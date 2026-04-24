# xoscar POC Notes

Scratch notes captured during Phase 0 of the Thespian→xoscar migration
(see `docs/prd-xoscar-migration.md` and
`/home/vscode/.claude/plans/cryptic-herding-cocoa.md`).

## Install (2026-04-24)

- `xoscar==0.9.5` installed from a prebuilt wheel via `uv sync`. **No C++
  build required** in the devcontainer. The PRD's concern about
  `cmake>=3.11`/`gcc>=8` only matters for sdist builds, which the wheel
  skips on glibc Linux / CPython 3.12.
- Transitive dependencies brought in: `cloudpickle`, `pandas`, `psutil`,
  `python-dateutil`, `scipy`, `six`, `tblib`, `uvloop`. `pandas` + `scipy`
  are surprisingly heavy for an actor framework — flag for removal
  consideration if they become a footprint concern later.
- `xoscar.__version__` reports `0.2.0.dev9+53.g8838185.dirty` because
  xoscar uses versioneer and resolves from the enclosing git checkout
  (maverick) rather than the installed wheel metadata. Cosmetic only.
  `importlib.metadata.version("xoscar")` correctly reports `0.9.5`.

## API surface confirmed

All the calls the plan depends on are exported from the top-level
`xoscar` namespace: `Actor`, `StatelessActor`, `create_actor_pool`,
`create_actor`, `actor_ref`, `destroy_actor`, `wait_for`, `generator`.

## Pivotal finding: event loop starvation blocks cross-process lookup

If the process hosting the xoscar pool spawns a subprocess via
``subprocess.Popen`` + ``communicate()`` (or any blocking call), the
pool's TCP server cannot service the subprocess's
``xo.actor_ref(address, uid)`` call. The subprocess connects at the
TCP layer (``ss`` shows an established socket) but xoscar's
``ActorRefMessage`` is never processed until the parent returns to
its asyncio loop — in practice the subprocess hangs indefinitely or
until its own ``wait_for`` timeout fires.

Fix: the parent MUST use ``asyncio.create_subprocess_exec`` (or
equivalent) so the pool's accept loop keeps running concurrently with
the child. With that change, a subprocess ``xo.actor_ref`` call
completes in ``<10 ms`` on loopback.

Implications for Phase 1:

- ``maverick serve-inbox`` is spawned by the ACP executor via
  ``McpServerStdio`` (agent-client-protocol). That path is already
  async-native, so the natural wiring is safe. We should add a note to
  ``serve_inbox`` that it must never be spawned via blocking
  ``subprocess.run``/``Popen.communicate`` by any of our own code.
- Tests that need a subprocess to reach an in-test xoscar pool must
  drive the subprocess via ``asyncio.create_subprocess_exec``.

## Validated behaviours (xoscar 0.9.5)

- ``@xo.generator async def`` on an ``xo.Actor`` streams across a ref
  via ``async for x in await ref.method(...)``. Plain
  ``AsyncGenerator`` returns without the decorator do NOT stream.
- ``xo.wait_for(ref.method(...), timeout=...)`` cancels the running
  actor coroutine cleanly — the actor method observes
  ``asyncio.CancelledError`` and can re-raise after bookkeeping.
- ``await xo.destroy_actor(ref)`` runs ``__pre_destroy__`` before the
  actor is removed. ``await pool.stop()`` alone does not invoke the
  hook per actor, confirming the plan's explicit-destroy discipline.
- Two pools created with ``address="127.0.0.1:0"`` bind to distinct
  ephemeral ports — concurrent workflows can coexist without port
  coordination (PRD goal G-5 trivially satisfied).

## Test-directory name collision with the ``xoscar`` package

Creating ``tests/unit/actors/xoscar/__init__.py`` turns that directory
into a Python package named ``xoscar``. pytest's default "prepend"
import mode puts the test file's parent on ``sys.path``, so
``import xoscar as xo`` from *any* production module imported during
collection then resolves to the empty test package instead of the
third-party ``xoscar`` install — tests collect as
``AttributeError: module 'xoscar' has no attribute 'Actor'``.

Fix: name test directories ``xoscar_runtime/`` (or similar). The
production subpackage ``src/maverick/actors/xoscar/`` is fine because
it is always reached fully-qualified as
``maverick.actors.xoscar.*``; only the test-dir bare name collides.

## Open items

(Populated as the POC + Phase 1 work surfaces behaviour worth
remembering.)
