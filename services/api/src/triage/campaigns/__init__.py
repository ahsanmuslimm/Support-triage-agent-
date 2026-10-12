"""Campaign optimization and personalization module."""

from .budget import BudgetAllocator
from .channel import ChannelSelector
from .incentive import IncentiveMatrixGenerator
from .optimizer import CampaignOptimizer
from .performance import PerformanceMonitor
from .send_time import SendTimeOptimizer

__all__ = [
    "BudgetAllocator",
    "CampaignOptimizer",
    "ChannelSelector",
    "IncentiveMatrixGenerator",
    "PerformanceMonitor",
    "SendTimeOptimizer",
]
