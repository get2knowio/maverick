"""Parameter echo activity for demonstrating parameter accessor usage."""

from dataclasses import asdict

from temporalio import activity

from src.models.parameters import Parameters
from src.utils.logging import get_structured_logger
from src.utils.param_accessor import get_required_param


# Structured logger for this activity
logger = get_structured_logger("activity.param_echo")


@activity.defn(name="echo_parameters")
async def echo_parameters(params: Parameters) -> dict[str, str]:
    """Echo parameters to demonstrate typed parameter accessor.

    This activity demonstrates how any workflow step can access
    parameters by key using the typed parameter accessor utility.

    Args:
        params: Workflow parameters

    Returns:
        Dictionary with echoed parameters and access method used
    """
    logger.info("param_echo_started", workflow_info=activity.info().workflow_id if activity.info() else "unknown")

    # Convert parameters to dict for accessor
    params_dict = asdict(params)

    # Demonstrate accessing github_repo_url using typed accessor
    github_repo_url = get_required_param(params_dict, "github_repo_url", str, "GitHub repository URL")

    result = {
        "github_repo_url": github_repo_url,
        "access_method": "typed_parameter_accessor",
        "parameter_count": str(len(params_dict)),
    }

    logger.info("param_echo_completed", github_repo_url=github_repo_url, parameter_count=len(params_dict))

    return result
