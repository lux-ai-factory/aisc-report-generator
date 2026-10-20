"""The built-in block types."""
from .ai_card import AiCardBlock
from .changes_since import ChangesSinceBlock
from .chapter import AppendixBlock, ChapterBlock
from .chart import ChartBlock
from .control_answers import ControlAnswersBlock
from .control_objectives import ControlObjectivesBlock
from .cover import CoverBlock
from .dashboard_chart import DashboardChartBlock
from .free_text import FreeTextBlock
from .key_figures import KeyFiguresBlock
from .risk_classification import RiskClassificationBlock
from .summary_coverage import SummaryCoverageBlock
from .test_results import TestResultsBlock
from .test_runs import TestRunsBlock

BUILTIN_BLOCKS = [CoverBlock, AiCardBlock, RiskClassificationBlock, ControlObjectivesBlock, TestResultsBlock,
                  ControlAnswersBlock, DashboardChartBlock, SummaryCoverageBlock, FreeTextBlock, ChapterBlock,
                  AppendixBlock, ChartBlock, KeyFiguresBlock, ChangesSinceBlock, TestRunsBlock]
