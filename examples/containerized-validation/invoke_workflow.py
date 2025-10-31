#!/usr/bin/env python3
"""Example script to invoke the readiness workflow with Docker Compose integration.

This demonstrates how to programmatically start the workflow with containerized
validation using the Temporal Python SDK.

Usage:
    python invoke_workflow.py

Requirements:
    - Temporal dev server running: temporal server start-dev
    - Maverick worker running: uv run maverick-worker
    - Docker Compose V2 available: docker compose version
"""

import asyncio
import sys
from datetime import datetime
from pathlib import Path

import yaml
from temporalio.client import Client

# Add project root to path to import Maverick modules
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.models.compose import ComposeConfig
from src.models.parameters import Parameters
from src.workflows.readiness import ReadinessWorkflow


async def main() -> None:
    """Run the readiness workflow with Docker Compose integration."""
    
    # Configuration
    compose_file_path = Path(__file__).parent / "docker-compose.yml"
    github_repo_url = "https://github.com/get2knowio/maverick"
    temporal_host = "localhost:7233"
    task_queue = "maverick-task-queue"
    
    # Load and parse Docker Compose file
    print(f"Loading compose file: {compose_file_path}")
    
    if not compose_file_path.exists():
        print(f"Error: Compose file not found: {compose_file_path}")
        sys.exit(1)
    
    with open(compose_file_path, "r") as f:
        yaml_content = f.read()
    
    try:
        parsed_config = yaml.safe_load(yaml_content)
    except yaml.YAMLError as e:
        print(f"Error parsing YAML: {e}")
        sys.exit(1)
    
    # Create workflow parameters
    compose_config = ComposeConfig(
        yaml_content=yaml_content,
        parsed_config=parsed_config,
        target_service="app",  # Explicitly specify (or omit to use default selection)
        startup_timeout_seconds=300,  # 5 minutes for environment startup
        validation_timeout_seconds=60,  # 1 minute per validation step
    )
    
    params = Parameters(
        github_repo_url=github_repo_url,
        compose_config=compose_config,
    )
    
    print(f"\nWorkflow parameters:")
    print(f"  Repository: {github_repo_url}")
    print(f"  Target service: {compose_config.target_service}")
    print(f"  Startup timeout: {compose_config.startup_timeout_seconds}s")
    print(f"  Validation timeout: {compose_config.validation_timeout_seconds}s")
    
    # Connect to Temporal
    print(f"\nConnecting to Temporal at {temporal_host}...")
    
    try:
        client = await Client.connect(temporal_host)
        print("✓ Connected to Temporal")
    except Exception as e:
        print(f"✗ Failed to connect to Temporal: {e}")
        print("\nMake sure Temporal dev server is running:")
        print("  temporal server start-dev")
        sys.exit(1)
    
    # Generate workflow ID with timestamp
    workflow_id = f"readiness-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    
    print(f"\nStarting workflow: {workflow_id}")
    print("This may take a few minutes while the container starts and health checks complete...\n")
    
    try:
        # Execute workflow and wait for result
        result = await client.execute_workflow(
            ReadinessWorkflow.run,
            params,
            id=workflow_id,
            task_queue=task_queue,
        )
        
        # Display results
        print("=" * 70)
        print("WORKFLOW COMPLETED")
        print("=" * 70)
        print(f"\nOverall Status: {result.overall_status}")
        
        if result.target_service:
            print(f"Target Service: {result.target_service}")
        
        # Display individual check results
        print("\nChecks:")
        for check in result.results:
            status_icon = "✓" if check.status == "pass" else "✗"
            print(f"  {status_icon} {check.tool}: {check.status}")
            if check.message:
                print(f"     {check.message}")
        
        # Display repo verification if present
        if result.repo_verification:
            status_icon = "✓" if result.repo_verification.status == "pass" else "✗"
            print(f"  {status_icon} Repository Access: {result.repo_verification.status}")
            if result.repo_verification.message:
                print(f"     {result.repo_verification.message}")
        
        # Display cleanup information
        print("\nEnvironment:")
        if result.target_service:
            print(f"  Validated in containerized environment (service: {result.target_service})")
        
        if result.cleanup_instructions:
            print("\n⚠ Cleanup Required:")
            print(f"  {result.cleanup_instructions}")
        else:
            print("  Environment cleaned up successfully")
        
        # Exit with appropriate code
        if result.overall_status == "ready":
            print("\n✓ All checks passed!")
            sys.exit(0)
        else:
            print("\n✗ Some checks failed")
            sys.exit(1)
    
    except Exception as e:
        print(f"\n✗ Workflow execution failed: {e}")
        print("\nTroubleshooting:")
        print("  1. Check worker is running: uv run maverick-worker")
        print("  2. Check Docker is available: docker compose version")
        print("  3. Check compose file syntax: docker compose -f docker-compose.yml config")
        print(f"  4. View workflow in Temporal UI: http://localhost:8233/namespaces/default/workflows/{workflow_id}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
