"""Sprint 8: ML Pipeline & Continuous Learning.

S8.1: Dataset Builder & Curation
S8.2: SetFit Fine-Tuning
S8.3: Temperature Scaling & ONNX Export
S8.4: Out-of-Distribution Detector
S8.5: MLflow Registry & Promotion
S8.6: Taxonomy Bootstrap
S8.7: Nightly Eval Suite
S8.8: Drift Monitoring
"""

from .calibration_onnx import (
    CalibrationMetrics,
    CalibrationPipeline,
    ECEComputer,
    HotReloader,
    ONNXExporter,
    ONNXInference,
    PlattScaling,
)
from .dataset_builder import (
    ClassBalancer,
    ConversationRecord,
    Deduplicator,
    GoldenSetTagger,
    LabeledExample,
    LabelSource,
    PIIScrubber,
    TrainTestSplitter,
)
from .drift_monitoring import (
    CentroidDriftDetector,
    ConceptDriftDetector,
    DriftMetrics,
    DriftMonitor,
    OODRateMonitor,
    PSIComputer,
)
from .mlflow_registry import (
    CanaryDeployment,
    ModelMetadata,
    PromotionGateEvaluator,
    PromotionStage,
    PromotionWorkflow,
    ShadowDualPredictor,
)
from .nightly_eval_suite import (
    NightlyEvalSuite,
    PromptfooEvaluator,
    PromptVersioning,
    RagasEvaluator,
    RegressionDetector,
)
from .ood_detector import (
    CentroidDetector,
    EnergyDetector,
    OODAnalyzer,
    OODEnsemble,
    OODMetrics,
    ThresholdCalibrator,
)
from .setfit_finetuner import (
    ContrastiveLoss,
    FocalLoss,
    HyperparameterTuner,
    LoRAAdapter,
    MultiLabelHead,
    SetFitTrainer,
    TrainingConfig,
    TrainingMetrics,
)
from .taxonomy_bootstrap import (
    ClusterAnalysis,
    ClusterLabel,
    MergeOperation,
    SplitOperation,
    TaxonomyBootstrapper,
)

__all__ = [
    # S8.1
    "ConversationRecord",
    "LabeledExample",
    "Deduplicator",
    "ClassBalancer",
    "TrainTestSplitter",
    "GoldenSetTagger",
    "PIIScrubber",
    # S8.2
    "SetFitTrainer",
    "TrainingConfig",
    "TrainingMetrics",
    "MultiLabelHead",
    "FocalLoss",
    "ContrastiveLoss",
    "LoRAAdapter",
    "HyperparameterTuner",
    # S8.3
    "PlattScaling",
    "ECEComputer",
    "ONNXExporter",
    "ONNXInference",
    "HotReloader",
    "CalibrationPipeline",
    "CalibrationMetrics",
    # S8.4
    "OODEnsemble",
    "EnergyDetector",
    "CentroidDetector",
    "ThresholdCalibrator",
    "OODAnalyzer",
    "OODMetrics",
    # S8.5
    "PromotionGateEvaluator",
    "ShadowDualPredictor",
    "CanaryDeployment",
    "PromotionWorkflow",
    "ModelMetadata",
    "PromotionStage",
    # S8.6
    "TaxonomyBootstrapper",
    "ClusterLabel",
    "ClusterAnalysis",
    "MergeOperation",
    "SplitOperation",
    # S8.7
    "RagasEvaluator",
    "PromptfooEvaluator",
    "RegressionDetector",
    "PromptVersioning",
    "NightlyEvalSuite",
    # S8.8
    "DriftMonitor",
    "PSIComputer",
    "CentroidDriftDetector",
    "OODRateMonitor",
    "ConceptDriftDetector",
    "DriftMetrics",
]
