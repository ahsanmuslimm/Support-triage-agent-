Feature: J2 - Multi-intent with Partial Autonomy and Handoff
  Scenario: Refund request exceeds auto-limit
    @pending
    Given a customer requests a refund for $240
    When the auto-refund limit is $150
    Then the system creates an approval request
    And a supervisor approves in Slack
    And the refund is processed via Stripe
