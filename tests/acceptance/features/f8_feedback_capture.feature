Feature: F8 - Feedback Capture
  Scenario: Customer provides helpful feedback
    @pending
    Given a conversation has been resolved
    When the customer rates the resolution as helpful
    Then the feedback is recorded with timestamp
    And it's associated with the conversation and triage run
