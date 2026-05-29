from __future__ import annotations

from dataclasses import dataclass, field

import pytest


FULL_REPORT_KEY = pytest.StashKey["TestNarrative"]()
FULL_MODE = False
TERMINAL_REPORTER = None


@dataclass
class TestNarrative:
    checked: str = ""
    setup: str = ""
    observed: str = ""
    steps: list[str] = field(default_factory=list)

    def set_checked(self, text: str) -> None:
        self.checked = text

    def set_setup(self, text: str) -> None:
        self.setup = text

    def set_observed(self, text: str) -> None:
        self.observed = text

    def add_step(self, text: str) -> None:
        self.steps.append(text)


def pytest_addoption(parser: pytest.Parser) -> None:
    group = parser.getgroup("jurispeed")
    group.addoption(
        "--simple",
        action="store_true",
        default=False,
        help="Usa la salida clasica de pytest con progreso por archivo y puntos.",
    )
    group.addoption(
        "--full",
        action="store_true",
        default=False,
        help="Muestra un resumen explicativo por cada test aprobado.",
    )


def pytest_configure(config: pytest.Config) -> None:
    global FULL_MODE
    is_simple = bool(config.getoption("simple"))
    is_full = bool(config.getoption("full"))

    if is_simple and is_full:
        raise pytest.UsageError(
            "Las opciones --simple y --full son mutuamente excluyentes. "
            "Usa solo una de ellas por ejecucion."
        )

    if is_simple:
        config.option.verbose = 0

    FULL_MODE = is_full


def pytest_sessionstart(session: pytest.Session) -> None:
    global TERMINAL_REPORTER
    TERMINAL_REPORTER = session.config.pluginmanager.get_plugin("terminalreporter")


@pytest.fixture
def test_report(request: pytest.FixtureRequest) -> TestNarrative:
    narrative = TestNarrative()
    request.node.stash[FULL_REPORT_KEY] = narrative
    return narrative


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo[object]) -> object:
    outcome = yield
    report = outcome.get_result()
    if call.when == "call":
        report.full_narrative = item.stash.get(FULL_REPORT_KEY, None)


def pytest_runtest_logreport(report: pytest.TestReport) -> None:
    global FULL_MODE, TERMINAL_REPORTER
    if report.when != "call" or not report.passed:
        return

    if not FULL_MODE:
        return

    narrative = getattr(report, "full_narrative", None)
    if not isinstance(narrative, TestNarrative):
        return

    if TERMINAL_REPORTER is None:
        return

    lines = []
    if narrative.checked:
        lines.append(f"  Que se revisó: {narrative.checked}")
    if narrative.setup:
        lines.append(f"  Input / setup: {narrative.setup}")
    if narrative.observed:
        lines.append(f"  Resultado recibido: {narrative.observed}")
    if narrative.steps:
        lines.append("  Flow / Siguiente paso:")
        lines.extend(f"    - {step}" for step in narrative.steps)

    if not lines:
        return

    TERMINAL_REPORTER.write_line("")
    for line in lines:
        TERMINAL_REPORTER.write_line(line)
    TERMINAL_REPORTER.write_line("")
