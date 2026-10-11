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

from .dataset_builder import (
    ConversationRecord,
    LabeledExample,
    Deduplicator,
    ClassBalancer,
    TrainTestSplitter,
    GoldenSetTagger,
    PIIScrubber,
    LabelSource,
)
from .setfit_finetuner import (
    SetFitTrainer,
    TrainingConfig,
    TrainingMetrics,
    MultiLabelHead,
    FocalLoss,
    ContrastiveLoss,
    LoRAAdapter,
    HyperparameterTuner,
)
from .calibration_onnx import (
    PlattScaling,
    ECEComputer,
    ONNXExporter,
    ONNXInference,
    HotReloader,
    CalibrationPipeline,
    CalibrationMetrics,
)
from .ood_detector import (
    OODEnsemble,
    EnergyDetector,
    CentroidDetector,
    ThresholdCalibrator,
    OODAnalyzer,
    OODMetrics,
)
from .mlflow_registry import (
    PromotionGateEvaluator,
    ShadowDualPredictor,
    CanaryDeployment,
    PromotionWorkflow,
    ModelMetadata,
    PromotionStage,
)
from .taxonomy_bootstrap import (
    TaxonomyBootstrapper,
    ClusterLabel,
    ClusterAnalysis,
    MergeOperation,
    SplitOperation,
)
from .nightly_eval_suite import (
    RagasEvaluator,
    PromptfooEvaluator,
    RegressionDetector,
    PromptVersioning,
    NightlyEvalSuite,
)
from .drift_monitoring import (
    DriftMonitor,
    PSIComputer,
    CentroidDriftDetector,
    OODRateMonitor,
    ConceptDriftDetector,
    DriftMetrics,
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
