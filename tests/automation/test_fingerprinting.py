"""
Tests for enhanced fingerprinting and anti-bot detection features.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from playwright.async_api import Page, BrowserContext

from kagebunshin.automation.fingerprinting import (
    apply_fingerprint_profile,
    apply_fingerprint_profile_to_context,
    get_random_fingerprint_profile
)


@pytest.fixture
def mock_page():
    """Create a mock Page object."""
    page = AsyncMock(spec=Page)
    page.add_init_script = AsyncMock()
    page.set_extra_http_headers = AsyncMock()
    return page


@pytest.fixture
def mock_context():
    """Create a mock BrowserContext object."""
    context = AsyncMock(spec=BrowserContext)
    context.add_init_script = AsyncMock()
    context.set_extra_http_headers = AsyncMock()
    return context


class TestFingerprintingEnhancements:
    """Test the enhanced anti-bot detection features."""

    @pytest.mark.asyncio
    async def test_javascript_environment_hardening_applied(self, mock_page):
        """Test that JavaScript environment hardening is applied to pages."""
        await apply_fingerprint_profile(mock_page)
        
        # Verify add_init_script was called
        mock_page.add_init_script.assert_called_once()
        
        # Get the script content
        script_content = mock_page.add_init_script.call_args[0][0]
        
        # Check for JavaScript Environment Hardening features
        assert "JavaScript Environment Hardening" in script_content
        assert "nativeFunctions.forEach" in script_content
        assert "originalError" in script_content
        assert "console[method]" in script_content
        
    @pytest.mark.asyncio
    async def test_cdp_detection_masking_applied(self, mock_page):
        """Test that CDP detection masking is applied to pages."""
        await apply_fingerprint_profile(mock_page)
        
        script_content = mock_page.add_init_script.call_args[0][0]
        
        # Check for CDP Detection & Masking features
        assert "CDP Detection & Masking" in script_content
        assert "__playwright" in script_content
        assert "__puppeteer" in script_content
        assert "key.startsWith('cdc_')" in script_content  # Dynamic pattern matching
        assert "chrome.runtime" in script_content
        
    @pytest.mark.asyncio
    async def test_core_fingerprint_randomization_applied(self, mock_page):
        """Test that core fingerprint randomization is applied to pages."""
        await apply_fingerprint_profile(mock_page)
        
        script_content = mock_page.add_init_script.call_args[0][0]
        
        # Check for Core Fingerprint Randomization features
        assert "Core Fingerprint Randomization" in script_content
        assert "RTCPeerConnection" in script_content
        assert "getBattery" in script_content
        assert "navigator.permissions.query" in script_content
        assert "enumerateDevices" in script_content
        
    @pytest.mark.asyncio
    async def test_context_level_fingerprinting_applied(self, mock_context):
        """Test that fingerprinting is applied at the context level."""
        profile = await apply_fingerprint_profile_to_context(mock_context)
        
        # Verify context methods were called
        mock_context.add_init_script.assert_called_once()
        mock_context.set_extra_http_headers.assert_called_once()
        
        # Verify profile is returned
        assert profile is not None
        assert "name" in profile
        assert "user_agent" in profile
        
    @pytest.mark.asyncio
    async def test_all_enhancements_in_context_script(self, mock_context):
        """Test that all enhancements are included in context-level script."""
        await apply_fingerprint_profile_to_context(mock_context)
        
        script_content = mock_context.add_init_script.call_args[0][0]
        
        # Check all enhancement categories are present
        assert "JavaScript Environment Hardening" in script_content
        assert "CDP Detection & Masking" in script_content
        assert "Core Fingerprint Randomization" in script_content
        
    @pytest.mark.asyncio
    async def test_webdriver_masking_still_present(self, mock_page):
        """Test that original webdriver masking is still present."""
        await apply_fingerprint_profile(mock_page)
        
        script_content = mock_page.add_init_script.call_args[0][0]
        
        # Check that webdriver masking is still there
        assert "navigator.webdriver" in script_content
        assert "get: () => false" in script_content
        
    @pytest.mark.asyncio
    async def test_canvas_fingerprinting_still_present(self, mock_page):
        """Test that original canvas fingerprinting protection is still present."""
        await apply_fingerprint_profile(mock_page)
        
        script_content = mock_page.add_init_script.call_args[0][0]
        
        # Check that canvas protection is still there
        assert "HTMLCanvasElement.prototype.toDataURL" in script_content
        assert "CanvasRenderingContext2D.prototype.getImageData" in script_content
        
    @pytest.mark.asyncio
    async def test_profile_specific_values_applied(self, mock_page):
        """Test that profile-specific values are correctly applied."""
        # Use a specific profile with known values
        with patch('kagebunshin.automation.fingerprinting.random.choice') as mock_choice:
            mock_profile = {
                "name": "Test_Profile",
                "user_agent": "Test-Agent/1.0",
                "screen": {"width": 1920, "height": 1080, "colorDepth": 24, "pixelDepth": 24},
                "hardware": {"cores": 8, "memory": 16, "platform": "Test32"},
                "timezone_offset": -300,
                "language_list": ["en-US", "en"],
                "headers": {}
            }
            mock_choice.return_value = mock_profile
            
            await apply_fingerprint_profile(mock_page)
            
            script_content = mock_page.add_init_script.call_args[0][0]
            
            # Check that profile values are in the script
            assert "1920" in script_content  # screen width
            assert "1080" in script_content  # screen height
            assert "8" in script_content     # cores
            assert "16" in script_content    # memory
            assert "-300" in script_content  # timezone
            
    def test_random_fingerprint_profile_selection(self):
        """Test that random fingerprint profile selection works."""
        profile1 = get_random_fingerprint_profile(seed=42)
        profile2 = get_random_fingerprint_profile(seed=42)
        profile3 = get_random_fingerprint_profile(seed=43)
        
        # Same seed should return same profile
        assert profile1 == profile2
        
        # Different seed might return different profile
        # (Could be same due to small profile list, but at least test it works)
        assert profile3 is not None
        assert "name" in profile3
        
    @pytest.mark.asyncio
    async def test_error_handling_in_script(self, mock_page):
        """Test that the injected script includes proper error handling."""
        await apply_fingerprint_profile(mock_page)
        
        script_content = mock_page.add_init_script.call_args[0][0]
        
        # Check for try-catch blocks
        assert "try {" in script_content
        assert "} catch (e) {" in script_content
        assert "/* ignore */" in script_content
        
    @pytest.mark.asyncio
    async def test_http_headers_set_correctly(self, mock_page):
        """Test that HTTP headers are set correctly with fingerprint profile."""
        await apply_fingerprint_profile(mock_page)
        
        # Verify headers were set
        mock_page.set_extra_http_headers.assert_called_once()
        
        headers = mock_page.set_extra_http_headers.call_args[0][0]
        
        # Check for expected headers
        assert "User-Agent" in headers
        assert "Accept" in headers
        assert "Accept-Encoding" in headers
        assert "Sec-Fetch-Dest" in headers
        
    @pytest.mark.asyncio
    async def test_plugin_spoofing_enhanced(self, mock_page):
        """Test that plugin spoofing is enhanced and still works."""
        await apply_fingerprint_profile(mock_page)
        
        script_content = mock_page.add_init_script.call_args[0][0]
        
        # Check for plugin spoofing - check for the actual plugin names first
        assert "Chrome PDF Plugin" in script_content
        assert "Chrome PDF Viewer" in script_content
        assert "Native Client" in script_content
        # Then check that navigator.plugins is being defined
        assert "Object.defineProperty(navigator, 'plugins'" in script_content
        
    @pytest.mark.asyncio
    async def test_dynamic_cdp_artifact_removal(self, mock_page):
        """Test that CDP artifacts are removed dynamically, not hardcoded."""
        await apply_fingerprint_profile(mock_page)
        
        script_content = mock_page.add_init_script.call_args[0][0]
        
        # Should use dynamic pattern matching
        assert "Object.keys(window).forEach" in script_content
        assert "key.startsWith('cdc_')" in script_content
        # Should NOT have hardcoded specific strings
        assert "cdc_adoQpoasnfa76pfcZLmcfl" not in script_content
        
    @pytest.mark.asyncio
    async def test_randomized_webgl_spoofing(self, mock_page):
        """Test that WebGL spoofing uses randomized values."""
        await apply_fingerprint_profile(mock_page)
        
        script_content = mock_page.add_init_script.call_args[0][0]
        
        # Should have randomization logic
        assert "const vendors =" in script_content
        assert "const renderers =" in script_content
        assert "Math.floor(Math.random()" in script_content
        # Should NOT have hardcoded specific GPU
        assert "Mesa DRI Intel(R) Ivybridge Mobile" not in script_content
        
    @pytest.mark.asyncio
    async def test_randomized_media_devices(self, mock_page):
        """Test that MediaDevices uses randomized device IDs."""
        await apply_fingerprint_profile(mock_page)
        
        script_content = mock_page.add_init_script.call_args[0][0]
        
        # Should have device ID generation logic
        assert "generateDeviceId" in script_content
        assert "generateGroupId" in script_content
        assert "Math.random().toString(36)" in script_content
        # Should NOT have hardcoded 'default'
        assert "deviceId: 'default'" not in script_content