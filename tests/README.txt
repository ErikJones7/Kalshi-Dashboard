Checks that run on your own computer with no network and no real money.

  python3 tests/test_helper.py     the helper against a fake Kalshi (order format, allocation rules, refusals, money bookkeeping)
  python3 tests/test_page.py       the page in a headless browser (the Kalshi cash guard, sizing, the warning on the real Auto card)

test_helper.py copies the helper into a temporary folder first, so your own data, keys and settings are never touched.
Run both after changing the page or the helper. Both print PASS or FAIL for each check and finish with "all passed" when nothing failed.
