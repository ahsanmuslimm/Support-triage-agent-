"""Team efficiency analyzer orchestrator."""

from typing import Dict
import logging

from .kpi import KPICalculator
from .skill_gap import SkillGapDetector
from .benchmarking import PeerBenchmarker
from .training import TrainingRecommender

logger = logging.getLogger(__name__)


class TeamEfficiencyAnalyzer:
    """Orchestrate team efficiency analysis."""

    def __init__(self):
        """Initialize analyzer."""
        self.kpi_calc = KPICalculator()
        self.skill_gap = SkillGapDetector()
        self.benchmarker = PeerBenchmarker()
        self.training = TrainingRecommender()

    async def analyze_team_efficiency(
        self, team_id: int, period: tuple
    ) -> Dict:
        """Analyze team efficiency."""
        kpis = await self.kpi_calc.batch_calculate_team_kpis(team_id, period)
        return {"team_kpis": kpis}
