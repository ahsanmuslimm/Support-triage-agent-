Feature: F4 - Clarification Flow
  Scenario: Missing entity triggers clarification question
    @pending
    Given a customer asks about an order without providing an order ID
    When the system needs an order ID to proceed
    Then the system asks one clarifying question
    And the customer provides the order ID
    And the system resolves the query
