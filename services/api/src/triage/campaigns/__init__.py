"""Campaign optimization and personalization module."""

from .optimizer import CampaignOptimizer
from .incentive import IncentiveMatrixGenerator
from .budget import BudgetAllocator
from .send_time import SendTimeOptimizer
from .channel import ChannelSelector
from .performance import PerformanceMonitor

__all__ = [
    "CampaignOptimizer",
    "IncentiveMatrixGenerator",
    "BudgetAllocator",
    "SendTimeOptimizer",
    "ChannelSelector",
    "PerformanceMonitor",
]
