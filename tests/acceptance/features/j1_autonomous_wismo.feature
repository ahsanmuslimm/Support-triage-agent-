Feature: J1 - Autonomous WISMO Resolution
  As a customer
  I want to know where my order is
  So that I have visibility on delivery

  @pending
  Scenario: Order status inquiry in chat
    Given a customer is in a chat session with verified email
    When the customer asks "Where's my order #48213?"
    Then the system detects intent "order.status" with confidence > 0.95
    And the system retrieves tracking from Shopify
    And the system composes a grounded answer with tracking link
    And the system sends the reply in < 4 seconds
    And the conversation is auto-resolved
    And a CSAT survey is sent

  @pending
  Scenario: Order status for premium customer
    Given a premium tier customer in a chat session
    When the customer asks "Track order ABC-123"
    Then the system responds with live tracking data
    And the response includes estimated delivery date
    And the conversation is marked as resolved
