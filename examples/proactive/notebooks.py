"""Build and execute the three notebooks in fresh kernels using this interpreter."""

import argparse
import hashlib
import json
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
TITLES = ("Anticipate a deadline", "Investigate and prepare quietly", "Reconsider ongoing goals")
NAMES = ("01-anticipate", "02-investigate", "03-reconsider")


def build():
    import nbformat

    directory = HERE / "notebooks"
    directory.mkdir(exist_ok=True)
    for level, (title, name) in enumerate(zip(TITLES, NAMES, strict=True), 1):
        cells = [
            nbformat.v4.new_markdown_cell(
                f"# {title}\n\n"
                "A proactive agent pursues a standing goal as time and circumstances change. "
                "This notebook uses synthetic meetings and local tools. No model calls, "
                "credentials or external accounts are used.\n\n"
                "Install the repository and `examples/proactive/requirements.txt` in your "
                "kernel environment. See [the tutorial](../README.md) for the conceptual "
                "explanation, diagrams, citations and limitations."
            ),
            nbformat.v4.new_code_cell(
                "import sys\nfrom pathlib import Path\n\n"
                "root = next(p for p in [Path.cwd(), *Path.cwd().parents] "
                "if (p / 'src/noema').is_dir())\n"
                "if str(root) not in sys.path:\n    sys.path.insert(0, str(root))"
            ),
            nbformat.v4.new_code_cell(
                f"from examples.proactive.lessons import run_lesson\n\nlevel = {level}"
            ),
            nbformat.v4.new_markdown_cell(
                "## Read the actual policy\n\n"
                "These functions are shared business code, not framework-provided behavior. "
                "Source is displayed so a small invocation does not hide its implementation."
            ),
            nbformat.v4.new_code_cell(
                "import inspect\n\nfrom examples.proactive.domain import Tools, proposals\n\n"
                "print(inspect.getsource(proposals))\nprint(inspect.getsource(Tools.invoke))"
            ),
            nbformat.v4.new_markdown_cell(
                "## Run the Noema implementation\n\n"
                "The scenario asserts useful action and appropriate silence."
            ),
            nbformat.v4.new_code_cell(
                "from IPython.display import display\n\n"
                "result = await run_lesson('noema', level)\n"
                "display(result['calls'])\ndisplay(result['notices'])\n"
                "assert len(result['notices']) == 1"
            ),
            nbformat.v4.new_markdown_cell(
                "## Inspect the SDK bridge\n\n"
                "NoemaLesson is a tutorial adapter, not an SDK API. Its source uses real "
                "ActionIntent, AutonomousAgent, NoemaSystem, policy and capability APIs."
            ),
            nbformat.v4.new_code_cell(
                "from examples.proactive.noema_agent import NoemaLesson\n\n"
                "print(inspect.getsource(NoemaLesson))"
            ),
            nbformat.v4.new_markdown_cell(
                "## Reproduce with ADK and LangGraph\n\n"
                "Each equivalent executes its own framework. Compare tool calls, notices "
                "and final state, not incompatible raw event formats."
            ),
            nbformat.v4.new_code_cell(
                "equivalents = {}\n"
                "for framework in ('adk', 'langgraph'):\n"
                "    other = await run_lesson(framework, level)\n"
                "    for key in ('calls', 'notices', 'world'):\n"
                "        assert other[key] == result[key], (framework, key)\n"
                "    equivalents[framework] = {'calls': len(other['calls']), "
                "'notices': len(other['notices'])}\n"
                "display(equivalents)"
            ),
            nbformat.v4.new_markdown_cell(
                "## Change the circumstances\n\n"
                "Run an independent case where a meeting is cancelled before its window. "
                "Change `cancelled` to False to observe how that changes eligibility."
            ),
            nbformat.v4.new_code_cell(
                "tools = Tools({'design:v1': 'A synthetic agenda'})\n"
                "agent = await NoemaLesson(level, tools).start()\n"
                "cancelled = {'start': 10, 'revision': 1, 'importance': 5, 'cancelled': True}\n"
                "try:\n"
                "    await agent.tick(now=4, meetings={'design': cancelled})\n"
                "    await agent.tick(now=5)\n"
                "    assert tools.notices == []\n"
                "    display(tools.calls)\n"
                "finally:\n    await agent.close()"
            ),
        ]
        if level == 3:
            cells += [
                nbformat.v4.new_markdown_cell(
                    "## Measure instead of assuming an advantage\n\n"
                    "Physical line counts and AST statement counts measure different things. "
                    "The shared policy, tools and host code count toward every implementation. "
                    "Native traces show a domain-semantic benefit in Noema; this does not "
                    "establish greater reliability or fewer source lines."
                ),
                nbformat.v4.new_code_cell(
                    "from examples.proactive.comparison import compare\n\n"
                    "measurement, traces = await compare()\n"
                    "display(measurement['code_totals'])\n"
                    "display(measurement['native_noema_records_in_medium_lesson'])\n"
                    "causal_key = ('native_noema_authorization_and_success_"
                    "have_observed_causal_parents')\n"
                    "assert measurement[causal_key]"
                ),
                nbformat.v4.new_markdown_cell(
                    "Process persistence is tested separately with `python -m unittest "
                    "tests.test_proactive_examples -v`. A notebook kernel remaining alive "
                    "is not process-restart evidence. Mid-effect crashes and durable "
                    "timer rearming are outside this tutorial's demonstrated guarantees."
                ),
            ]
        notebook = nbformat.v4.new_notebook(
            cells=cells,
            metadata={
                "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
                "language_info": {"name": "python", "version": "3.12"},
            },
        )
        for index, cell in enumerate(notebook.cells):
            cell.id = f"{name}-{index:02}"
        nbformat.write(notebook, directory / f"{name}.ipynb")


def execute():
    import nbformat
    from jupyter_client import KernelManager
    from jupyter_client.kernelspec import KernelSpecManager
    from nbclient import NotebookClient

    receipts = []
    with tempfile.TemporaryDirectory() as directory:
        kernel = Path(directory) / "python3"
        kernel.mkdir()
        (kernel / "kernel.json").write_text(
            json.dumps(
                {
                    "argv": [sys.executable, "-m", "ipykernel_launcher", "-f", "{connection_file}"],
                    "display_name": "Isolated tutorial interpreter",
                    "language": "python",
                }
            )
        )
        for name in NAMES:
            path = HERE / "notebooks" / f"{name}.ipynb"
            notebook = nbformat.read(path, as_version=4)
            manager = KernelManager(
                kernel_name="python3",
                kernel_spec_manager=KernelSpecManager(
                    kernel_dirs=[directory],
                    ensure_native_kernel=False,
                ),
            )
            client = NotebookClient(
                notebook, km=manager, timeout=90, resources={"metadata": {"path": str(ROOT)}}
            )
            try:
                client.execute()
            finally:
                if manager.has_kernel:
                    manager.shutdown_kernel(now=True)
            nbformat.validate(notebook)
            nbformat.write(notebook, path)
            receipts.append(
                {
                    "notebook": path.name,
                    "status": "passed_fresh_kernel",
                    "code_cells": sum(cell.cell_type == "code" for cell in notebook.cells),
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                }
            )
    observed = HERE / "observed"
    observed.mkdir(exist_ok=True)
    (observed / "notebooks.json").write_text(json.dumps(receipts, indent=2) + "\n")
    print(json.dumps(receipts, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--build", action="store_true")
    arguments = parser.parse_args()
    if arguments.build:
        build()
    if arguments.execute:
        execute()
    if not arguments.build and not arguments.execute:
        parser.error("specify --build or --execute")
