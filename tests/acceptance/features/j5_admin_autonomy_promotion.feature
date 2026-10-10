Feature: J5 - Admin Autonomy Promotion
  Scenario: Admin promotes intent to full auto
    @pending
    Given an admin user is in the tuning console
    When they promote "password_reset" intent to full_auto
    Then the autonomy level is updated immediately
    And subsequent password reset requests are auto-resolved without draft
