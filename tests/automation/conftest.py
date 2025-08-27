"""
Playwright fixtures for browser automation tests.
"""

import pytest
from playwright.sync_api import Playwright, Browser, BrowserContext, Page


@pytest.fixture(scope="session")
def playwright():
    """Create Playwright instance for the session."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        yield p


@pytest.fixture(scope="session")
def browser(playwright: Playwright):
    """Create a browser instance for the session."""
    browser = playwright.chromium.launch(headless=True)
    yield browser
    browser.close()


@pytest.fixture
def context(browser: Browser):
    """Create a browser context for each test."""
    context = browser.new_context()
    yield context
    context.close()


@pytest.fixture
def page(context: BrowserContext):
    """Create a page for each test."""
    page = context.new_page()
    yield page
    page.close()