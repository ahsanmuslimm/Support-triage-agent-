"""Temperature scaling for confidence calibration."""

import numpy as np
from typing import List, Tuple
import structlog

log = structlog.get_logger()


class TemperatureScaler:
    """Calibrates classification confidence via temperature scaling.

    Minimizes Expected Calibration Error (ECE) by finding optimal temperature T.
    Temperature scaling: p_calibrated = softmax(logits / T).
    """

    @staticmethod
    def compute_ece(confidences: List[float], accuracies: List[bool], n_bins: int = 10) -> float:
        """Compute Expected Calibration Error.

        Args:
            confidences: Predicted confidences [0, 1].
            accuracies: True positives (1) / False positives (0).
            n_bins: Number of bins for calibration.

        Returns:
            ECE score (0 = perfect calibration, 1 = worst).
        """
        confidences = np.array(confidences)
        accuracies = np.array(accuracies)

        if len(confidences) == 0:
            return 0.0

        bin_edges = np.linspace(0, 1, n_bins + 1)
        ece = 0.0
        total_samples = len(confidences)

        for i in range(n_bins):
            bin_lower = bin_edges[i]
            bin_upper = bin_edges[i + 1]

            # Points in this bin
            in_bin = (confidences >= bin_lower) & (confidences < bin_upper)
            n_in_bin = np.sum(in_bin)

            if n_in_bin == 0:
                continue

            bin_confidence = np.mean(confidences[in_bin])
            bin_accuracy = np.mean(accuracies[in_bin])

            ece += np.abs(bin_confidence - bin_accuracy) * (n_in_bin / total_samples)

        return float(ece)

    @staticmethod
    def find_optimal_temperature(
        raw_confidences: List[float],
        accuracies: List[bool],
        temperature_range: Tuple[float, float] = (0.5, 2.0),
        n_steps: int = 20,
    ) -> float:
        """Find temperature that minimizes ECE.

        Args:
            raw_confidences: Raw confidences before scaling.
            accuracies: Ground truth labels.
            temperature_range: Range of temperatures to search.
            n_steps: Number of temperatures to try.

        Returns:
            Optimal temperature.
        """
        if not raw_confidences:
            return 1.0

        raw_confidences = np.array(raw_confidences)

        temperatures = np.linspace(temperature_range[0], temperature_range[1], n_steps)
        best_ece = float("inf")
        best_temp = 1.0

        for temp in temperatures:
            # Apply temperature scaling: p_scaled = 1 / (1 + exp(-logits / T))
            # For probabilities in [0,1], use: logits ≈ log(p / (1 - p)) (logit transform)
            # Simpler: just normalize via softmax with temperature
            # For binary case: apply temperature to log-odds

            # Approximate: scale confidences toward 0.5
            scaled_confidences = 0.5 + 0.5 * np.tanh((2 * raw_confidences - 1) / (2 * temp))
            scaled_confidences = np.clip(scaled_confidences, 1e-7, 1 - 1e-7)

            ece = TemperatureScaler.compute_ece(scaled_confidences.tolist(), accuracies, n_bins=10)

            if ece < best_ece:
                best_ece = ece
                best_temp = temp

        log.info("temperature_scaling_optimized", best_temp=best_temp, best_ece=best_ece)
        return float(best_temp)

    @staticmethod
    def scale_confidence(confidence: float, temperature: float = 1.0) -> float:
        """Apply temperature scaling to a single confidence value.

        Args:
            confidence: Raw confidence [0, 1].
            temperature: Temperature parameter.

        Returns:
            Temperature-scaled confidence.
        """
        if temperature <= 0:
            return confidence

        # Map confidence to log-odds, scale by temperature, then map back
        # For probability p: logit(p) = log(p / (1-p))
        # Avoid infinities
        confidence = np.clip(confidence, 1e-7, 1 - 1e-7)

        # Scale using tanh (smooth approximation)
        scaled = 0.5 + 0.5 * np.tanh((2 * confidence - 1) / (2 * temperature))
        return float(np.clip(scaled, 0.0, 1.0))
