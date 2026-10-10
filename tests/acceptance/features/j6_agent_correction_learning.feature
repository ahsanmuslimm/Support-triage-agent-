Feature: J6 - Agent Correction & Learning
  Scenario: Agent corrects system misclassification
    @pending
    Given the system misclassifies an intent
    When an agent corrects it and provides feedback
    Then the correction is recorded in the audit log
    And it contributes to model retraining
