# Crawl4AI Code Context

Generated on 2026-05-15


## File: crawl4ai/async_configs.py


```py
import copy
import functools
import importlib
import os
import warnings
import requests
from .config import (
    DEFAULT_PROVIDER,
    DEFAULT_PROVIDER_API_KEY,
    MIN_WORD_THRESHOLD,
    IMAGE_DESCRIPTION_MIN_WORD_THRESHOLD,
    PROVIDER_MODELS,
    PROVIDER_MODELS_PREFIXES,
    SCREENSHOT_HEIGHT_TRESHOLD,
    PAGE_TIMEOUT,
    IMAGE_SCORE_THRESHOLD,
    SOCIAL_MEDIA_DOMAINS,
)

from .user_agent_generator import UAGen, ValidUAGenerator  # , OnlineUAGenerator
from .extraction_strategy import ExtractionStrategy, LLMExtractionStrategy
from .chunking_strategy import ChunkingStrategy, RegexChunking

from .markdown_generation_strategy import MarkdownGenerationStrategy, DefaultMarkdownGenerator
from .content_scraping_strategy import ContentScrapingStrategy, LXMLWebScrapingStrategy
from .deep_crawling import DeepCrawlStrategy
from .table_extraction import TableExtractionStrategy, DefaultTableExtraction

from .cache_context import CacheMode
from .proxy_strategy import ProxyRotationStrategy

import inspect
from typing import Any, Awaitable, Callable, Dict, List, Optional, Union
from enum import Enum

# Type alias for URL matching
UrlMatcher = Union[str, Callable[[str], bool], List[Union[str, Callable[[str], bool]]]]


def _with_defaults(cls):
    """Class decorator: adds set_defaults/get_defaults/reset_defaults classmethods.

    After decorating, every new instance resolves parameters as:
        explicit arg  >  class-level user defaults  >  hardcoded default

    Usage::

        BrowserConfig.set_defaults(headless=False, viewport_width=1920)
        cfg = BrowserConfig()          # headless=False, viewport_width=1920
        cfg = BrowserConfig(headless=True)  # explicit wins → headless=True
    """
    original_init = cls.__init__
    sig = inspect.signature(original_init)
    param_names = [p for p in sig.parameters if p != "self"]
    valid_params = frozenset(param_names)

    @functools.wraps(original_init)
    def wrapped_init(self, *args, **kwargs):
        user_defaults = type(self)._user_defaults
        if user_defaults:
            # Determine which params the caller passed explicitly
            explicit = set(kwargs.keys())
            for i in range(len(args)):
                if i < len(param_names):
                    explicit.add(param_names[i])
            # Inject user defaults for non-explicit params
            for key, value in user_defaults.items():
                if key not in explicit:
                    kwargs[key] = copy.deepcopy(value)
        original_init(self, *args, **kwargs)

    cls.__init__ = wrapped_init
    cls._user_defaults = {}

    @classmethod
    def set_defaults(klass, **kwargs):
        """Set class-level default overrides for new instances.

        Args:
            **kwargs: Parameter names and their default values.

        Raises:
            ValueError: If any key is not a valid ``__init__`` parameter.
        """
        invalid = set(kwargs) - valid_params
        if invalid:
            raise ValueError(
                f"Invalid parameter(s) for {klass.__name__}: {invalid}"
            )
        for k, v in kwargs.items():
            klass._user_defaults[k] = copy.deepcopy(v)

    @classmethod
    def get_defaults(klass):
        """Return a deep copy of the current class-level defaults."""
        return copy.deepcopy(klass._user_defaults)

    @classmethod
    def reset_defaults(klass, *names):
        """Clear class-level defaults.

        With no arguments, removes all overrides.
        With arguments, removes only the named overrides.
        """
        if names:
            for n in names:
                klass._user_defaults.pop(n, None)
        else:
            klass._user_defaults.clear()

    cls.set_defaults = set_defaults
    cls.get_defaults = get_defaults
    cls.reset_defaults = reset_defaults
    return cls


class MatchMode(Enum):
    OR = "or"
    AND = "and"

# from .proxy_strategy import ProxyConfig

# Allowlist of types that can be deserialized via from_serializable_dict().
# This prevents arbitrary class instantiation from untrusted input (e.g. API requests).
ALLOWED_DESERIALIZE_TYPES = {
    # Config classes
    "BrowserConfig", "CrawlerRunConfig", "HTTPCrawlerConfig",
    "LLMConfig", "ProxyConfig", "GeolocationConfig",
    "SeedingConfig", "VirtualScrollConfig", "LinkPreviewConfig",
    # Extraction strategies
    "JsonCssExtractionStrategy", "JsonXPathExtractionStrategy",
    "JsonLxmlExtractionStrategy", "LLMExtractionStrategy",
    "CosineStrategy", "RegexExtractionStrategy",
    # Markdown / content
    "DefaultMarkdownGenerator",
    "PruningContentFilter", "BM25ContentFilter", "LLMContentFilter",
    # Scraping
    "LXMLWebScrapingStrategy", "PDFContentScrapingStrategy",
    # Chunking
    "RegexChunking",
    # Deep crawl
    "BFSDeepCrawlStrategy", "DFSDeepCrawlStrategy", "BestFirstCrawlingStrategy",
    # Filters & scorers
    "FilterChain", "URLPatternFilter", "DomainFilter",
    "ContentTypeFilter", "URLFilter", "SEOFilter", "ContentRelevanceFilter",
    "KeywordRelevanceScorer", "URLScorer", "CompositeScorer",
    "DomainAuthorityScorer", "FreshnessScorer", "PathDepthScorer",
    # Enums
    "CacheMode", "MatchMode", "DisplayMode",
    # Dispatchers
    "MemoryAdaptiveDispatcher", "SemaphoreDispatcher",
    # Table extraction
    "DefaultTableExtraction", "NoTableExtraction",
    # Proxy
    "RoundRobinProxyStrategy",
}


def to_serializable_dict(obj: Any, ignore_default_value : bool = False):
    """
    Recursively convert an object to a serializable dictionary using {type, params} structure
    for complex objects.
    """
    if obj is None:
        return None

    # Handle basic types
    if isinstance(obj, (str, int, float, bool)):
        return obj

    # Handle Enum
    if isinstance(obj, Enum):
        return {"type": obj.__class__.__name__, "params": obj.value}

    # Handle datetime objects
    if hasattr(obj, "isoformat"):
        return obj.isoformat()

    # Handle lists, tuples, and sets, and basically any iterable
    if isinstance(obj, (list, tuple, set)) or hasattr(obj, '__iter__') and not isinstance(obj, dict):
        return [to_serializable_dict(item) for item in obj]

    # Handle frozensets, which are not iterable
    if isinstance(obj, frozenset):
        return [to_serializable_dict(item) for item in list(obj)]

    # Handle dictionaries - preserve them as-is
    if isinstance(obj, dict):
        return {
            "type": "dict",  # Mark as plain dictionary
            "value": {str(k): to_serializable_dict(v) for k, v in obj.items()},
        }

    _type = obj.__class__.__name__

    # Handle class instances
    if hasattr(obj, "__class__"):
        # Skip types that cannot be deserialized (e.g. logging.Logger, callables).
        # Only serialize objects whose type is in ALLOWED_DESERIALIZE_TYPES so that
        # from_serializable_dict can reconstruct them on the other side.
        if _type not in ALLOWED_DESERIALIZE_TYPES:
            return None

        # Get constructor signature
        sig = inspect.signature(obj.__class__.__init__)
        params = sig.parameters

        # Get current values
        current_values = {}
        for name, param in params.items():
            if name == "self":
                continue

            value = getattr(obj, name, param.default)

            # Only include if different from default, considering empty values
            if not (is_empty_value(value) and is_empty_value(param.default)):
                if value != param.default and not ignore_default_value:
                    current_values[name] = to_serializable_dict(value)
        
        # Don't serialize private __slots__ - they're internal implementation details
        # not constructor parameters. This was causing URLPatternFilter to fail
        # because _simple_suffixes was being serialized as 'simple_suffixes'
        # if hasattr(obj, '__slots__'):
        #     for slot in obj.__slots__:
        #         if slot.startswith('_'):  # Handle private slots
        #             attr_name = slot[1:]  # Remove leading '_'
        #             value = getattr(obj, slot, None)
        #             if value is not None:
        #                 current_values[attr_name] = to_serializable_dict(value)

        return {
            "type": obj.__class__.__name__,
            "params": current_values
        }
        
    return str(obj)


def from_serializable_dict(data: Any) -> Any:
    """
    Recursively convert a serializable dictionary back to an object instance.
    """
    if data is None:
        return None

    # Handle basic types
    if isinstance(data, (str, int, float, bool)):
        return data

    # Handle typed data.
    # Only enter the typed-object path for dicts that match the shapes produced
    # by to_serializable_dict(): {"type": "<ClassName>", "params": {...}} or
    # {"type": "dict", "value": {...}}.  Plain business dicts that happen to
    # carry a "type" key (e.g. JSON-Schema fragments, JsonCss field specs like
    # {"type": "text", "name": "..."}) have neither "params" nor "value" and
    # must fall through to the raw-dict path below so they are passed as data.
    if (
        isinstance(data, dict)
        and "type" in data
        and ("params" in data or (data["type"] == "dict" and "value" in data))
    ):
        # Handle plain dictionaries
        if data["type"] == "dict" and "value" in data:
            return {k: from_serializable_dict(v) for k, v in data["value"].items()}

        # Security: only allow known-safe types to be deserialized.
        # Unknown types (e.g. logging.Logger serialized by older clients) are
        # silently dropped (returned as None) instead of crashing the request.
        type_name = data["type"]
        if type_name not in ALLOWED_DESERIALIZE_TYPES:
            return None

        cls = None
        module_paths = ["crawl4ai"]
        for module_path in module_paths:
            try:
                mod = importlib.import_module(module_path)
                if hasattr(mod, type_name):
                    cls = getattr(mod, type_name)
                    break
            except (ImportError, AttributeError):
                continue

        if cls is not None:
            # Handle Enum
            if issubclass(cls, Enum):
                return cls(data["params"])

            if "params" in data:
                # Handle class instances
                constructor_args = {
                    k: from_serializable_dict(v) for k, v in data["params"].items()
                }
                return cls(**constructor_args)

    # Handle lists
    if isinstance(data, list):
        return [from_serializable_dict(item) for item in data]

    # Handle raw dictionaries (legacy support)
    if isinstance(data, dict):
        return {k: from_serializable_dict(v) for k, v in data.items()}

    return data


def is_empty_value(value: Any) -> bool:
    """Check if a value is effectively empty/null."""
    if value is None:
        return True
    if isinstance(value, (list, tuple, set, dict, str)) and len(value) == 0:
        return True
    return False

class GeolocationConfig:
    def __init__(
        self,
        latitude: float,
        longitude: float,
        accuracy: Optional[float] = 0.0
    ):
        """Configuration class for geolocation settings.
        
        Args:
            latitude: Latitude coordinate (e.g., 37.7749)
            longitude: Longitude coordinate (e.g., -122.4194)
            accuracy: Accuracy in meters. Default: 0.0
        """
        self.latitude = latitude
        self.longitude = longitude
        self.accuracy = accuracy
    
    @staticmethod
    def from_dict(geo_dict: Dict) -> "GeolocationConfig":
        """Create a GeolocationConfig from a dictionary."""
        return GeolocationConfig(
            latitude=geo_dict.get("latitude"),
            longitude=geo_dict.get("longitude"),
            accuracy=geo_dict.get("accuracy", 0.0)
        )
    
    def to_dict(self) -> Dict:
        """Convert to dictionary representation."""
        return {
            "latitude": self.latitude,
            "longitude": self.longitude,
            "accuracy": self.accuracy
        }
    
    def clone(self, **kwargs) -> "GeolocationConfig":
        """Create a copy of this configuration with updated values.

        Args:
            **kwargs: Key-value pairs of configuration options to update

        Returns:
            GeolocationConfig: A new instance with the specified updates
        """
        config_dict = self.to_dict()
        config_dict.update(kwargs)
        return GeolocationConfig.from_dict(config_dict)

class ProxyConfig:
    DIRECT = "direct"  # Sentinel: use in proxy_config list to mean "no proxy"

    def __init__(
        self,
        server: str,
        username: Optional[str] = None,
        password: Optional[str] = None,
        ip: Optional[str] = None,
    ):
        """Configuration class for a single proxy.

        Args:
            server: Proxy server URL (e.g., "http://127.0.0.1:8080")
            username: Optional username for proxy authentication
            password: Optional password for proxy authentication
            ip: Optional IP address for verification purposes
        """
        self.server = server
        self.username = username
        self.password = password

        # Extract IP from server if not explicitly provided
        self.ip = ip or self._extract_ip_from_server()
    
    def _extract_ip_from_server(self) -> Optional[str]:
        """Extract IP address from server URL."""
        try:
            # Simple extraction assuming http://ip:port format
            if "://" in self.server:
                parts = self.server.split("://")[1].split(":")
                return parts[0]
            else:
                parts = self.server.split(":")
                return parts[0]
        except Exception:
            return None
    
    @staticmethod
    def from_string(proxy_str: str) -> "ProxyConfig":
        """Create a ProxyConfig from a string.

        Supported formats:
        - 'http://username:password@ip:port'
        - 'http://ip:port'
        - 'socks5://ip:port'
        - 'ip:port:username:password'
        - 'ip:port'
        """
        s = (proxy_str or "").strip()
        # URL with credentials
        if "@" in s and "://" in s:
            auth_part, server_part = s.split("@", 1)
            protocol, credentials = auth_part.split("://", 1)
            if ":" in credentials:
                username, password = credentials.split(":", 1)
                return ProxyConfig(
                    server=f"{protocol}://{server_part}",
                    username=username,
                    password=password,
                )
        # URL without credentials (keep scheme)
        if "://" in s and "@" not in s:
            return ProxyConfig(server=s)
        # Colon separated forms
        parts = s.split(":")
        if len(parts) == 4:
            ip, port, username, password = parts
            return ProxyConfig(server=f"http://{ip}:{port}", username=username, password=password)
        if len(parts) == 2:
            ip, port = parts
            return ProxyConfig(server=f"http://{ip}:{port}")
        raise ValueError(f"Invalid proxy string format: {proxy_str}")
    
    @staticmethod
    def from_dict(proxy_dict: Dict) -> "ProxyConfig":
        """Create a ProxyConfig from a dictionary."""
        return ProxyConfig(
            server=proxy_dict.get("server"),
            username=proxy_dict.get("username"),
            password=proxy_dict.get("password"),
            ip=proxy_dict.get("ip"),
        )
    
    @staticmethod
    def from_env(env_var: str = "PROXIES") -> List["ProxyConfig"]:
        """Load proxies from environment variable.
        
        Args:
            env_var: Name of environment variable containing comma-separated proxy strings
            
        Returns:
            List of ProxyConfig objects
        """
        proxies = []
        try:
            proxy_list = os.getenv(env_var, "").split(",")
            for proxy in proxy_list:
                if not proxy:
                    continue
                proxies.append(ProxyConfig.from_string(proxy))
        except Exception as e:
            print(f"Error loading proxies from environment: {e}")
        return proxies
    
    def to_dict(self) -> Dict:
        """Convert to dictionary representation."""
        return {
            "server": self.server,
            "username": self.username,
            "password": self.password,
            "ip": self.ip,
        }
    
    def clone(self, **kwargs) -> "ProxyConfig":
        """Create a copy of this configuration with updated values.

        Args:
            **kwargs: Key-value pairs of configuration options to update

        Returns:
            ProxyConfig: A new instance with the specified updates
        """
        config_dict = self.to_dict()
        config_dict.update(kwargs)
        return ProxyConfig.from_dict(config_dict)

@_with_defaults
class BrowserConfig:
    """
    Configuration class for setting up a browser instance and its context in AsyncPlaywrightCrawlerStrategy.

    This class centralizes all parameters that affect browser and context creation. Instead of passing
    scattered keyword arguments, users can instantiate and modify this configuration object. The crawler
    code will then reference these settings to initialize the browser in a consistent, documented manner.

    Attributes:
        browser_type (str): The type of browser to launch. Supported values: "chromium", "firefox", "webkit".
                            Default: "chromium".
        headless (bool): Whether to run the browser in headless mode (no visible GUI).
                         Default: True.
        browser_mode (str): Determines how the browser should be initialized:
                           "builtin" - use the builtin CDP browser running in background
                           "dedicated" - create a new dedicated browser instance each time
                           "cdp" - use explicit CDP settings provided in cdp_url
                           "docker" - run browser in Docker container with isolation
                           Default: "dedicated"
        use_managed_browser (bool): Launch the browser using a managed approach (e.g., via CDP), allowing
                                    advanced manipulation. Default: False.
        cdp_url (str): URL for the Chrome DevTools Protocol (CDP) endpoint. Default: "ws://localhost:9222/devtools/browser/".
        browser_context_id (str or None): Pre-existing CDP browser context ID to use. When provided along with
                                          cdp_url, the crawler will reuse this context instead of creating a new one.
                                          Useful for cloud browser services that pre-create isolated contexts.
                                          Default: None.
        target_id (str or None): Pre-existing CDP target ID (page) to use. When provided along with
                                 browser_context_id, the crawler will reuse this target instead of creating
                                 a new page. Default: None.
        cdp_cleanup_on_close (bool): When True and using cdp_url, the close() method will still clean up
                                     the local Playwright client resources. Useful for cloud/server scenarios
                                     where you don't own the remote browser but need to prevent memory leaks
                                     from accumulated Playwright instances. Default: False.
        cdp_close_delay (float): Seconds to wait after disconnecting a CDP WebSocket before stopping the
                                 Playwright subprocess. Gives the connection time to fully release. Set to
                                 0 to skip the delay entirely. Only applies when cdp_cleanup_on_close=True.
                                 Default: 1.0.
        cache_cdp_connection (bool): When True and using cdp_url, the Playwright subprocess and CDP WebSocket
                                     are cached at the class level and shared across multiple BrowserManager
                                     instances connecting to the same cdp_url. Reference-counted; the connection
                                     is only closed when the last user releases it. Eliminates the overhead of
                                     repeated Playwright/CDP setup and teardown. Default: False.
        create_isolated_context (bool): When True and using cdp_url, forces creation of a new browser context
                                        instead of reusing the default context. Essential for concurrent crawls
                                        on the same browser to prevent navigation conflicts. Default: False.
        debugging_port (int): Port for the browser debugging protocol. Default: 9222.
        use_persistent_context (bool): Use a persistent browser context (like a persistent profile).
                                       Automatically sets use_managed_browser=True. Default: False.
        user_data_dir (str or None): Path to a user data directory for persistent sessions. If None, a
                                     temporary directory may be used. Default: None.
        chrome_channel (str): The Chrome channel to launch (e.g., "chrome", "msedge"). Only applies if browser_type
                              is "chromium". Default: "chromium".
        channel (str): The channel to launch (e.g., "chromium", "chrome", "msedge"). Only applies if browser_type
                              is "chromium". Default: "chromium".
        proxy (Optional[str]): Proxy server URL (e.g., "http://username:password@proxy:port"). If None, no proxy is used.
                             Default: None.
        proxy_config (ProxyConfig or dict or None): Detailed proxy configuration, e.g. {"server": "...", "username": "..."}.
                                     If None, no additional proxy config. Default: None.
        viewport_width (int): Default viewport width for pages. Default: 1080.
        viewport_height (int): Default viewport height for pages. Default: 600.
        viewport (dict): Default viewport dimensions for pages. If set, overrides viewport_width and viewport_height.
                         Default: None.
        device_scale_factor (float): The device pixel ratio used for rendering pages. Controls how many
                                     physical pixels map to one CSS pixel, allowing simulation of HiDPI
                                     or Retina displays. For example, a viewport of 1920x1080 with a
                                     device_scale_factor of 2.0 produces screenshots at 3840x2160 resolution.
                                     Increasing this value improves screenshot quality but may increase
                                     memory usage and rendering time.
                                     Default: 1.0.
        verbose (bool): Enable verbose logging.
                        Default: True.
        accept_downloads (bool): Whether to allow file downloads. If True, requires a downloads_path.
                                 Default: False.
        downloads_path (str or None): Directory to store downloaded files. If None and accept_downloads is True,
                                      a default path will be created. Default: None.
        storage_state (str or dict or None): An in-memory storage state (cookies, localStorage).
                                             Default: None.
        ignore_https_errors (bool): Ignore HTTPS certificate errors. Default: True.
        java_script_enabled (bool): Enable JavaScript execution in pages. Default: True.
        cookies (list): List of cookies to add to the browser context. Each cookie is a dict with fields like
                        {"name": "...", "value": "...", "url": "..."}.
                        Default: [].
        headers (dict): Extra HTTP headers to apply to all requests in this context.
                        Default: {}.
        user_agent (str): Custom User-Agent string to use. Default: "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                           "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Safari/537.36".
        user_agent_mode (str or None): Mode for generating the user agent (e.g., "random"). If None, use the provided
                                       user_agent as-is. Default: None.
        user_agent_generator_config (dict or None): Configuration for user agent generation if user_agent_mode is set.
                                                    Default: None.
        text_mode (bool): If True, disables images and other rich content for potentially faster load times.
                          Default: False.
        light_mode (bool): Disables certain background features for performance gains. Default: False.
        extra_args (list): Additional command-line arguments passed to the browser.
                           Default: [].
        enable_stealth (bool): If True, applies playwright-stealth to bypass basic bot detection.
                              Cannot be used with use_undetected browser mode. Default: False.
        memory_saving_mode (bool): If True, adds aggressive cache discard and V8 heap cap flags
                                   to reduce Chromium memory growth. Recommended for high-volume
                                   crawling (1000+ pages). May slightly reduce performance due to
                                   cache eviction. Default: False.
        max_pages_before_recycle (int): Number of pages to crawl before recycling the browser
                                        process to reclaim leaked memory. 0 = disabled.
                                        Recommended: 500-1000 for long-running crawlers.
                                        Default: 0.
        avoid_ads (bool): If True, blocks ad-related and tracker network requests at the
                          browser context level using a curated blocklist of top ad/tracker
                          domains. Default: False.
        avoid_css (bool): If True, blocks loading of CSS files (css, less, scss, sass) to
                          reduce resource usage and speed up crawling. Default: False.
    """

    def __init__(
        self,
        browser_type: str = "chromium",
        headless: bool = True,
        browser_mode: str = "dedicated",
        use_managed_browser: bool = False,
        cdp_url: str = None,
        browser_context_id: str = None,
        target_id: str = None,
        cdp_cleanup_on_close: bool = False,
        cdp_close_delay: float = 1.0,
        cache_cdp_connection: bool = False,
        create_isolated_context: bool = False,
        use_persistent_context: bool = False,
        user_data_dir: str = None,
        chrome_channel: str = "chromium",
        channel: str = "chromium",
        proxy: str = None,
        proxy_config: Union[ProxyConfig, dict, None] = None,
        viewport_width: int = 1080,
        viewport_height: int = 600,
        viewport: dict = None,
        device_scale_factor: float = 1.0,
        accept_downloads: bool = False,
        downloads_path: str = None,
        storage_state: Union[str, dict, None] = None,
        ignore_https_errors: bool = True,
        java_script_enabled: bool = True,
        sleep_on_close: bool = False,
        verbose: bool = False,
        cookies: list = None,
        headers: dict = None,
        user_agent: str = (
            # "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:109.0) AppleWebKit/537.36 "
            # "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            # "(KHTML, like Gecko) Chrome/116.0.5845.187 Safari/604.1 Edg/117.0.2045.47"
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/116.0.0.0 Safari/537.36"
        ),
        user_agent_mode: str = "",
        user_agent_generator_config: dict = {},
        text_mode: bool = False,
        light_mode: bool = False,
        extra_args: list = None,
        debugging_port: int = 9222,
        host: str = "localhost",
        enable_stealth: bool = False,
        avoid_ads: bool = False,
        avoid_css: bool = False,
        init_scripts: List[str] = None,
        memory_saving_mode: bool = False,
        max_pages_before_recycle: int = 0,
    ):
        
        self.browser_type = browser_type
        self.headless = headless
        self.browser_mode = browser_mode
        self.use_managed_browser = use_managed_browser
        self.cdp_url = cdp_url
        self.browser_context_id = browser_context_id
        self.target_id = target_id
        self.cdp_cleanup_on_close = cdp_cleanup_on_close
        self.cdp_close_delay = cdp_close_delay
        self.cache_cdp_connection = cache_cdp_connection
        self.create_isolated_context = create_isolated_context
        self.use_persistent_context = use_persistent_context
        self.user_data_dir = user_data_dir
        self.chrome_channel = chrome_channel or self.browser_type or "chromium"
        self.channel = channel or self.browser_type or "chromium"
        if self.browser_type in ["firefox", "webkit"]:
            self.channel = ""
            self.chrome_channel = ""
        if proxy:
            warnings.warn("The 'proxy' parameter is deprecated and will be removed in a future release. Use 'proxy_config' instead.", UserWarning)
        self.proxy = proxy
        self.proxy_config = proxy_config
        if isinstance(self.proxy_config, dict):
            self.proxy_config = ProxyConfig.from_dict(self.proxy_config)
        if isinstance(self.proxy_config, str):
            self.proxy_config = ProxyConfig.from_string(self.proxy_config)
        
        if self.proxy and self.proxy_config:
            warnings.warn("Both 'proxy' and 'proxy_config' are provided. 'proxy_config' will take precedence.", UserWarning)
            self.proxy = None
        elif self.proxy:
            # Convert proxy string to ProxyConfig if proxy_config is not provided
            self.proxy_config = ProxyConfig.from_string(self.proxy)
            self.proxy = None

        self.viewport_width = viewport_width
        self.viewport_height = viewport_height
        self.viewport = viewport
        if self.viewport is not None:
            self.viewport_width = self.viewport.get("width", 1080)
            self.viewport_height = self.viewport.get("height", 600)
        self.device_scale_factor = device_scale_factor
        self.accept_downloads = accept_downloads
        self.downloads_path = downloads_path
        self.storage_state = storage_state
        self.ignore_https_errors = ignore_https_errors
        self.java_script_enabled = java_script_enabled
        self.cookies = cookies if cookies is not None else []
        self.headers = headers if headers is not None else {}
        self.user_agent = user_agent
        self.user_agent_mode = user_agent_mode
        self.user_agent_generator_config = user_agent_generator_config
        self.text_mode = text_mode
        self.light_mode = light_mode
        self.extra_args = extra_args if extra_args is not None else []
        self.sleep_on_close = sleep_on_close
        self.verbose = verbose
        self.debugging_port = debugging_port
        self.host = host
        self.enable_stealth = enable_stealth
        self.avoid_ads = avoid_ads
        self.avoid_css = avoid_css
        self.init_scripts = init_scripts if init_scripts is not None else []
        self.memory_saving_mode = memory_saving_mode
        self.max_pages_before_recycle = max_pages_before_recycle

        fa_user_agenr_generator = ValidUAGenerator()
        if self.user_agent_mode == "random":
            self.user_agent = fa_user_agenr_generator.generate(
                **(self.user_agent_generator_config or {})
            )
        else:
            pass

        self.browser_hint = UAGen.generate_client_hints(self.user_agent)
        self.headers.setdefault("sec-ch-ua", self.browser_hint)

        # Set appropriate browser management flags based on browser_mode
        if self.browser_mode == "builtin":
            # Builtin mode uses managed browser connecting to builtin CDP endpoint
            self.use_managed_browser = True
            # cdp_url will be set later by browser_manager
        elif self.browser_mode == "docker":
            # Docker mode uses managed browser with CDP to connect to browser in container
            self.use_managed_browser = True
            # cdp_url will be set later by docker browser strategy
        elif self.browser_mode == "custom" and self.cdp_url:
            # Custom mode with explicit CDP URL
            self.use_managed_browser = True
        elif self.browser_mode == "dedicated":
            # Dedicated mode uses a new browser instance each time
            pass

        # If persistent context is requested, ensure managed browser is enabled
        if self.use_persistent_context:
            self.use_managed_browser = True
            
        # Validate stealth configuration
        if self.enable_stealth and self.use_managed_browser and self.browser_mode == "builtin":
            raise ValueError(
                "enable_stealth cannot be used with browser_mode='builtin'. "
                "Stealth mode requires a dedicated browser instance."
            )

    @staticmethod
    def from_kwargs(kwargs: dict) -> "BrowserConfig":
        # Auto-deserialize any dict values that use the {"type": ..., "params": ...}
        # serialization format (e.g. from JSON API requests or dump()/load() roundtrips).
        kwargs = {
            k: from_serializable_dict(v) if isinstance(v, dict) and "type" in v else v
            for k, v in kwargs.items()
        }
        # Only pass keys present in kwargs so that __init__ defaults (and
        # set_defaults() overrides) are respected for missing keys.
        valid = inspect.signature(BrowserConfig.__init__).parameters.keys() - {"self"}
        return BrowserConfig(**{k: v for k, v in kwargs.items() if k in valid})

    def to_dict(self):
        result = {
            "browser_type": self.browser_type,
            "headless": self.headless,
            "browser_mode": self.browser_mode,
            "use_managed_browser": self.use_managed_browser,
            "cdp_url": self.cdp_url,
            "browser_context_id": self.browser_context_id,
            "target_id": self.target_id,
            "cdp_cleanup_on_close": self.cdp_cleanup_on_close,
            "create_isolated_context": self.create_isolated_context,
            "use_persistent_context": self.use_persistent_context,
            "user_data_dir": self.user_data_dir,
            "chrome_channel": self.chrome_channel,
            "channel": self.channel,
            "proxy": self.proxy,
            "proxy_config": self.proxy_config.to_dict() if hasattr(self.proxy_config, 'to_dict') else self.proxy_config,
            "viewport_width": self.viewport_width,
            "viewport_height": self.viewport_height,
            "device_scale_factor": self.device_scale_factor,
            "accept_downloads": self.accept_downloads,
            "downloads_path": self.downloads_path,
            "storage_state": self.storage_state,
            "ignore_https_errors": self.ignore_https_errors,
            "java_script_enabled": self.java_script_enabled,
            "cookies": self.cookies,
            "headers": self.headers,
            "user_agent": self.user_agent,
            "user_agent_mode": self.user_agent_mode,
            "user_agent_generator_config": self.user_agent_generator_config,
            "text_mode": self.text_mode,
            "light_mode": self.light_mode,
            "extra_args": self.extra_args,
            "sleep_on_close": self.sleep_on_close,
            "verbose": self.verbose,
            "debugging_port": self.debugging_port,
            "host": self.host,
            "enable_stealth": self.enable_stealth,
            "avoid_ads": self.avoid_ads,
            "avoid_css": self.avoid_css,
            "init_scripts": self.init_scripts,
            "memory_saving_mode": self.memory_saving_mode,
            "max_pages_before_recycle": self.max_pages_before_recycle,
        }


        return result

    def clone(self, **kwargs):
        """Create a copy of this configuration with updated values.

        Args:
            **kwargs: Key-value pairs of configuration options to update

        Returns:
            BrowserConfig: A new instance with the specified updates
        """
        config_dict = self.to_dict()
        config_dict.update(kwargs)
        return BrowserConfig.from_kwargs(config_dict)

    # Create a funciton returns dict of the object
    def dump(self) -> dict:
        # Serialize the object to a dictionary
        return to_serializable_dict(self)

    @staticmethod
    def load(data: dict) -> "BrowserConfig":
        # Deserialize the object from a dictionary
        config = from_serializable_dict(data)
        if isinstance(config, BrowserConfig):
            return config
        return BrowserConfig.from_kwargs(config)

    def set_nstproxy(
        self,
        token: str,
        channel_id: str,
        country: str = "ANY",
        state: str = "",
        city: str = "",
        protocol: str = "http",
        session_duration: int = 10,
    ):
        """
        Fetch a proxy from NSTProxy API and automatically assign it to proxy_config.

        Get your NSTProxy token from: https://app.nstproxy.com/profile

        Args:
            token (str): NSTProxy API token.
            channel_id (str): NSTProxy channel ID.
            country (str, optional): Country code (default: "ANY").
            state (str, optional): State code (default: "").
            city (str, optional): City name (default: "").
            protocol (str, optional): Proxy protocol ("http" or "socks5"). Defaults to "http".
            session_duration (int, optional): Session duration in minutes (0 = rotate each request). Defaults to 10.

        Raises:
            ValueError: If the API response format is invalid.
            PermissionError: If the API returns an error message.
        """

        # --- Validate input early ---
        if not token or not channel_id:
            raise ValueError("[NSTProxy] token and channel_id are required")

        if protocol not in ("http", "socks5"):
            raise ValueError(f"[NSTProxy] Invalid protocol: {protocol}")

        # --- Build NSTProxy API URL ---
        params = {
            "fType": 2,
            "count": 1,
            "channelId": channel_id,
            "country": country,
            "protocol": protocol,
            "sessionDuration": session_duration,
            "token": token,
        }
        if state:
            params["state"] = state
        if city:
            params["city"] = city

        url = "https://api.nstproxy.com/api/v1/generate/apiproxies"

        try:
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()

            data = response.json()

            # --- Handle API error response ---
            if isinstance(data, dict) and data.get("err"):
                raise PermissionError(f"[NSTProxy] API Error: {data.get('msg', 'Unknown error')}")

            if not isinstance(data, list) or not data:
                raise ValueError("[NSTProxy] Invalid API response — expected a non-empty list")

            proxy_info = data[0]

            # --- Apply proxy config ---
            self.proxy_config = ProxyConfig(
                server=f"{protocol}://{proxy_info['ip']}:{proxy_info['port']}",
                username=proxy_info["username"],
                password=proxy_info["password"],
            )

        except Exception as e:
            print(f"[NSTProxy] ❌ Failed to set proxy: {e}")
            raise

class VirtualScrollConfig:
    """Configuration for virtual scroll handling.
    
    This config enables capturing content from pages with virtualized scrolling
    (like Twitter, Instagram feeds) where DOM elements are recycled as user scrolls.
    """
    
    def __init__(
        self,
        container_selector: str,
        scroll_count: int = 10,
        scroll_by: Union[str, int] = "container_height",
        wait_after_scroll: float = 0.5,
    ):
        """
        Initialize virtual scroll configuration.
        
        Args:
            container_selector: CSS selector for the scrollable container
            scroll_count: Maximum number of scrolls to perform
            scroll_by: Amount to scroll - can be:
                - "container_height": scroll by container's height
                - "page_height": scroll by viewport height  
                - int: fixed pixel amount
            wait_after_scroll: Seconds to wait after each scroll for content to load
        """
        self.container_selector = container_selector
        self.scroll_count = scroll_count
        self.scroll_by = scroll_by
        self.wait_after_scroll = wait_after_scroll
    
    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "container_selector": self.container_selector,
            "scroll_count": self.scroll_count,
            "scroll_by": self.scroll_by,
            "wait_after_scroll": self.wait_after_scroll,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "VirtualScrollConfig":
        """Create instance from dictionary."""
        return cls(**data)

class LinkPreviewConfig:
    """Configuration for link head extraction and scoring."""
    
    def __init__(
        self,
        include_internal: bool = True,
        include_external: bool = False,
        include_patterns: Optional[List[str]] = None,
        exclude_patterns: Optional[List[str]] = None,
        concurrency: int = 10,
        timeout: int = 5,
        max_links: int = 100,
        query: Optional[str] = None,
        score_threshold: Optional[float] = None,
        verbose: bool = False
    ):
        """
        Initialize link extraction configuration.
        
        Args:
            include_internal: Whether to include same-domain links
            include_external: Whether to include different-domain links  
            include_patterns: List of glob patterns to include (e.g., ["*/docs/*", "*/api/*"])
            exclude_patterns: List of glob patterns to exclude (e.g., ["*/login*", "*/admin*"])
            concurrency: Number of links to process simultaneously
            timeout: Timeout in seconds for each link's head extraction
            max_links: Maximum number of links to process (prevents overload)
            query: Query string for BM25 contextual scoring (optional)
            score_threshold: Minimum relevance score to include links (0.0-1.0, optional)
            verbose: Show detailed progress during extraction
        """
        self.include_internal = include_internal
        self.include_external = include_external
        self.include_patterns = include_patterns
        self.exclude_patterns = exclude_patterns
        self.concurrency = concurrency
        self.timeout = timeout
        self.max_links = max_links
        self.query = query
        self.score_threshold = score_threshold
        self.verbose = verbose
        
        # Validation
        if concurrency <= 0:
            raise ValueError("concurrency must be positive")
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        if max_links <= 0:
            raise ValueError("max_links must be positive")
        if score_threshold is not None and not (0.0 <= score_threshold <= 1.0):
            raise ValueError("score_threshold must be between 0.0 and 1.0")
        if not include_internal and not include_external:
            raise ValueError("At least one of include_internal or include_external must be True")
    
    @staticmethod
    def from_dict(config_dict: Dict[str, Any]) -> "LinkPreviewConfig":
        """Create LinkPreviewConfig from dictionary (for backward compatibility)."""
        if not config_dict:
            return None
        
        return LinkPreviewConfig(
            include_internal=config_dict.get("include_internal", True),
            include_external=config_dict.get("include_external", False),
            include_patterns=config_dict.get("include_patterns"),
            exclude_patterns=config_dict.get("exclude_patterns"),
            concurrency=config_dict.get("concurrency", 10),
            timeout=config_dict.get("timeout", 5),
            max_links=config_dict.get("max_links", 100),
            query=config_dict.get("query"),
            score_threshold=config_dict.get("score_threshold"),
            verbose=config_dict.get("verbose", False)
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary format."""
        return {
            "include_internal": self.include_internal,
            "include_external": self.include_external,
            "include_patterns": self.include_patterns,
            "exclude_patterns": self.exclude_patterns,
            "concurrency": self.concurrency,
            "timeout": self.timeout,
            "max_links": self.max_links,
            "query": self.query,
            "score_threshold": self.score_threshold,
            "verbose": self.verbose
        }
    
    def clone(self, **kwargs) -> "LinkPreviewConfig":
        """Create a copy with updated values."""
        config_dict = self.to_dict()
        config_dict.update(kwargs)
        return LinkPreviewConfig.from_dict(config_dict)


class HTTPCrawlerConfig:
    """HTTP-specific crawler configuration"""

    method: str = "GET"
    headers: Optional[Dict[str, str]] = None
    data: Optional[Dict[str, Any]] = None
    json: Optional[Dict[str, Any]] = None
    follow_redirects: bool = True
    verify_ssl: bool = True
    downloads_path: Optional[str] = None

    def __init__(
        self,
        method: str = "GET",
        headers: Optional[Dict[str, str]] = None,
        data: Optional[Dict[str, Any]] = None,
        json: Optional[Dict[str, Any]] = None,
        follow_redirects: bool = True,
        verify_ssl: bool = True,
        downloads_path: Optional[str] = None,
    ):
        self.method = method
        self.headers = headers
        self.data = data
        self.json = json
        self.follow_redirects = follow_redirects
        self.verify_ssl = verify_ssl
        self.downloads_path = downloads_path

    @staticmethod
    def from_kwargs(kwargs: dict) -> "HTTPCrawlerConfig":
        return HTTPCrawlerConfig(
            method=kwargs.get("method", "GET"),
            headers=kwargs.get("headers"),
            data=kwargs.get("data"),
            json=kwargs.get("json"),
            follow_redirects=kwargs.get("follow_redirects", True),
            verify_ssl=kwargs.get("verify_ssl", True),
            downloads_path=kwargs.get("downloads_path"),
        )

    def to_dict(self):
        return {
            "method": self.method,
            "headers": self.headers,
            "data": self.data,
            "json": self.json,
            "follow_redirects": self.follow_redirects,
            "verify_ssl": self.verify_ssl,
            "downloads_path": self.downloads_path,
        }

    def clone(self, **kwargs):
        """Create a copy of this configuration with updated values.

        Args:
            **kwargs: Key-value pairs of configuration options to update

        Returns:
            HTTPCrawlerConfig: A new instance with the specified updates
        """
        config_dict = self.to_dict()
        config_dict.update(kwargs)
        return HTTPCrawlerConfig.from_kwargs(config_dict)

    def dump(self) -> dict:
        return to_serializable_dict(self)

    @staticmethod
    def load(data: dict) -> "HTTPCrawlerConfig":
        config = from_serializable_dict(data)
        if isinstance(config, HTTPCrawlerConfig):
            return config
        return HTTPCrawlerConfig.from_kwargs(config)

@_with_defaults
class CrawlerRunConfig():

    """
    Configuration class for controlling how the crawler runs each crawl operation.
    This includes parameters for content extraction, page manipulation, waiting conditions,
    caching, and other runtime behaviors.

    This centralizes parameters that were previously scattered as kwargs to `arun()` and related methods.
    By using this class, you have a single place to understand and adjust the crawling options.

    Attributes:
        # Deep Crawl Parameters
        deep_crawl_strategy (DeepCrawlStrategy or None): Strategy to use for deep crawling.

        # Content Processing Parameters
        word_count_threshold (int): Minimum word count threshold before processing content.
                                    Default: MIN_WORD_THRESHOLD (typically 200).
        extraction_strategy (ExtractionStrategy or None): Strategy to extract structured data from crawled pages.
                                                          Default: None (NoExtractionStrategy is used if None).
        chunking_strategy (ChunkingStrategy): Strategy to chunk content before extraction.
                                              Default: RegexChunking().
        markdown_generator (MarkdownGenerationStrategy): Strategy for generating markdown.
                                                         Default: None.
        only_text (bool): If True, attempt to extract text-only content where applicable.
                          Default: False.
        css_selector (str or None): CSS selector to extract a specific portion of the page.
                                    Default: None.
        
        target_elements (list of str or None): List of CSS selectors for specific elements for Markdown generation 
                                                and structured data extraction. When you set this, only the contents 
                                                of these elements are processed for extraction and Markdown generation. 
                                                If you do not set any value, the entire page is processed. 
                                                The difference between this and css_selector is that this will shrink 
                                                the initial raw HTML to the selected element, while this will only affect 
                                                the extraction and Markdown generation.
                                    Default: None
        excluded_tags (list of str or None): List of HTML tags to exclude from processing.
                                             Default: None.
        excluded_selector (str or None): CSS selector to exclude from processing.
                                         Default: None.
        keep_data_attributes (bool): If True, retain `data-*` attributes while removing unwanted attributes.
                                     Default: False.
        keep_attrs (list of str): List of HTML attributes to keep during processing.
                                      Default: [].
        remove_forms (bool): If True, remove all `<form>` elements from the HTML.
                             Default: False.
        prettiify (bool): If True, apply `fast_format_html` to produce prettified HTML output.
                          Default: False.
        parser_type (str): Type of parser to use for HTML parsing.
                           Default: "lxml".
        scraping_strategy (ContentScrapingStrategy): Scraping strategy to use.
                           Default: LXMLWebScrapingStrategy.
        proxy_config (ProxyConfig or dict or None): Detailed proxy configuration, e.g. {"server": "...", "username": "..."}.
                                     If None, no additional proxy config. Default: None.

        # Sticky Proxy Session Parameters
        proxy_session_id (str or None): When set, maintains the same proxy for all requests sharing this session ID.
                                        The proxy is acquired on first request and reused for subsequent requests.
                                        Session expires when explicitly released or crawler context is closed.
                                        Default: None.
        proxy_session_ttl (int or None): Time-to-live for sticky session in seconds.
                                         After TTL expires, a new proxy is acquired on next request.
                                         Default: None (session lasts until explicitly released or crawler closes).
        proxy_session_auto_release (bool): If True, automatically release the proxy session after a batch operation.
                                           Useful for arun_many() to clean up sessions automatically.
                                           Default: False.

        # Browser Location and Identity Parameters
        locale (str or None): Locale to use for the browser context (e.g., "en-US").
                             Default: None.
        timezone_id (str or None): Timezone identifier to use for the browser context (e.g., "America/New_York").
                                  Default: None.
        geolocation (GeolocationConfig or None): Geolocation configuration for the browser.
                                                Default: None.

        # SSL Parameters
        fetch_ssl_certificate: bool = False,
        # Caching Parameters
        cache_mode (CacheMode or None): Defines how caching is handled.
                                        If None, defaults to CacheMode.ENABLED internally.
                                        Default: CacheMode.BYPASS.
        session_id (str or None): Optional session ID to persist the browser context and the created
                                  page instance. If the ID already exists, the crawler does not
                                  create a new page and uses the current page to preserve the state.
        bypass_cache (bool): Legacy parameter, if True acts like CacheMode.BYPASS.
                             Default: False.
        disable_cache (bool): Legacy parameter, if True acts like CacheMode.DISABLED.
                              Default: False.
        no_cache_read (bool): Legacy parameter, if True acts like CacheMode.WRITE_ONLY.
                              Default: False.
        no_cache_write (bool): Legacy parameter, if True acts like CacheMode.READ_ONLY.
                               Default: False.
        shared_data (dict or None): Shared data to be passed between hooks.
                                     Default: None.

        # Cache Validation Parameters (Smart Cache)
        check_cache_freshness (bool): If True, validates cached content freshness using HTTP
                                      conditional requests (ETag/Last-Modified) and head fingerprinting
                                      before returning cached results. Avoids full browser crawls when
                                      content hasn't changed. Only applies when cache_mode allows reads.
                                      Default: False.
        cache_validation_timeout (float): Timeout in seconds for cache validation HTTP requests.
                                          Default: 10.0.

        # Page Navigation and Timing Parameters
        wait_until (str): The condition to wait for when navigating, e.g. "domcontentloaded".
                          Default: "domcontentloaded".
        page_timeout (int): Timeout in ms for page operations like navigation.
                            Default: 60000 (60 seconds).
        wait_for (str or None): A CSS selector or JS condition to wait for before extracting content.
                                Default: None.
        wait_for_timeout (int or None): Specific timeout in ms for the wait_for condition.
                                       If None, uses page_timeout instead.
                                       Default: None.
        wait_for_images (bool): If True, wait for images to load before extracting content.
                                Default: False.
        delay_before_return_html (float): Delay in seconds before retrieving final HTML.
                                          Default: 0.1.
        mean_delay (float): Mean base delay between requests when calling arun_many.
                            Default: 0.1.
        max_range (float): Max random additional delay range for requests in arun_many.
                           Default: 0.3.
        semaphore_count (int): Number of concurrent operations allowed.
                               Default: 5.

        # Page Interaction Parameters
        js_code (str or list of str or None): JavaScript code/snippets to run on the page
                                              after wait_for and delay_before_return_html.
                                              Default: None.
        js_code_before_wait (str or list of str or None): JavaScript to run BEFORE wait_for.
                                              Use for triggering loading that wait_for then checks.
                                              Default: None.
        js_only (bool): If True, indicates subsequent calls are JS-driven updates, not full page loads.
                        Default: False.
        ignore_body_visibility (bool): If True, ignore whether the body is visible before proceeding.
                                       Default: True.
        scan_full_page (bool): If True, scroll through the entire page to load all content.
                               Default: False.
        scroll_delay (float): Delay in seconds between scroll steps if scan_full_page is True.
                              Default: 0.2.
        max_scroll_steps (Optional[int]): Maximum number of scroll steps to perform during full page scan.
                                         If None, scrolls until the entire page is loaded. Default: None.
        process_iframes (bool): If True, attempts to process and inline iframe content.
                                Default: False.
        flatten_shadow_dom (bool): If True, flatten shadow DOM content into the light DOM
                                    before HTML capture so page.content() includes it.
                                    Also injects an init script to force-open closed shadow roots.
                                    Default: False.
        remove_overlay_elements (bool): If True, remove overlays/popups before extracting HTML.
                                        Default: False.
        remove_consent_popups (bool): If True, remove GDPR/cookie consent popups (IAB TCF/CMP)
                                      before extracting HTML. Targets known CMP providers like
                                      OneTrust, Cookiebot, TrustArc, Quantcast, Didomi, etc.
                                      Default: False.
        simulate_user (bool): If True, simulate user interactions (mouse moves, clicks) for anti-bot measures.
                              Default: False.
        override_navigator (bool): If True, overrides navigator properties for more human-like behavior.
                                   Default: False.
        magic (bool): If True, attempts automatic handling of overlays/popups.
                      Default: False.
        adjust_viewport_to_content (bool): If True, adjust viewport according to the page content dimensions.
                                           Default: False.

        # Media Handling Parameters
        screenshot (bool): Whether to take a screenshot after crawling.
                           Default: False.
        screenshot_wait_for (float or None): Additional wait time before taking a screenshot.
                                             Default: None.
        screenshot_height_threshold (int): Threshold for page height to decide screenshot strategy.
                                           Default: SCREENSHOT_HEIGHT_TRESHOLD (from config, e.g. 20000).
        force_viewport_screenshot (bool): If True, always take viewport-only screenshots regardless of page height.
                                          When False, uses automatic decision (viewport for short pages, full-page for long pages).
                                          Default: False.
        pdf (bool): Whether to generate a PDF of the page.
                    Default: False.
        image_description_min_word_threshold (int): Minimum words for image description extraction.
                                                    Default: IMAGE_DESCRIPTION_MIN_WORD_THRESHOLD (e.g., 50).
        image_score_threshold (int): Minimum score threshold for processing an image.
                                     Default: IMAGE_SCORE_THRESHOLD (e.g., 3).
        exclude_external_images (bool): If True, exclude all external images from processing.
                                         Default: False.
        table_score_threshold (int): Minimum score threshold for processing a table.
                                     Default: 7.
        table_extraction (TableExtractionStrategy): Strategy to use for table extraction.
                                     Default: DefaultTableExtraction with table_score_threshold.

        # Virtual Scroll Parameters
        virtual_scroll_config (VirtualScrollConfig or dict or None): Configuration for handling virtual scroll containers.
                                                                     Used for capturing content from pages with virtualized 
                                                                     scrolling (e.g., Twitter, Instagram feeds).
                                                                     Default: None.

        # Link and Domain Handling Parameters
        exclude_social_media_domains (list of str): List of domains to exclude for social media links.
                                                    Default: SOCIAL_MEDIA_DOMAINS (from config).
        exclude_external_links (bool): If True, exclude all external links from the results.
                                       Default: False.
        exclude_internal_links (bool): If True, exclude internal links from the results.
                                       Default: False.
        exclude_social_media_links (bool): If True, exclude links pointing to social media domains.
                                           Default: False.
        exclude_domains (list of str): List of specific domains to exclude from results.
                                       Default: [].
        exclude_internal_links (bool): If True, exclude internal links from the results.
                                       Default: False.
        score_links (bool): If True, calculate intrinsic quality scores for all links using URL structure,
                           text quality, and contextual relevance metrics. Separate from link_preview_config.
                           Default: False.

        # Debugging and Logging Parameters
        verbose (bool): Enable verbose logging.
                        Default: True.
        log_console (bool): If True, log console messages from the page.
                            Default: False.

        # HTTP Crwler Strategy Parameters
        method (str): HTTP method to use for the request, when using AsyncHTTPCrwalerStrategy.
                        Default: "GET".
        data (dict): Data to send in the request body, when using AsyncHTTPCrwalerStrategy.
                        Default: None.
        json (dict): JSON data to send in the request body, when using AsyncHTTPCrwalerStrategy.

        # Connection Parameters
        stream (bool): If True, enables streaming of crawled URLs as they are processed when used with arun_many.
                      Default: False.
        process_in_browser (bool): If True, forces raw:/file:// URLs to be processed through the browser
                                   pipeline (enabling js_code, wait_for, scrolling, etc.). When False (default),
                                   raw:/file:// URLs use a fast path that returns HTML directly without browser
                                   interaction. This is automatically enabled when browser-requiring parameters
                                   are detected (js_code, wait_for, screenshot, pdf, etc.).
                                   Default: False.

        check_robots_txt (bool): Whether to check robots.txt rules before crawling. Default: False
                                 Default: False.
        user_agent (str): Custom User-Agent string to use.
                          Default: None.
        user_agent_mode (str or None): Mode for generating the user agent (e.g., "random"). If None, use the provided user_agent as-is.
                                       Default: None.
        user_agent_generator_config (dict or None): Configuration for user agent generation if user_agent_mode is set.
                                                    Default: None.

        # Experimental Parameters
        experimental (dict): Dictionary containing experimental parameters that are in beta phase.
                            This allows passing temporary features that are not yet fully integrated 
                            into the main parameter set.
                            Default: None.

        url: str = None  # This is not a compulsory parameter
    """
    _UNWANTED_PROPS = {
        'disable_cache' : 'Instead, use cache_mode=CacheMode.DISABLED',
        'bypass_cache' : 'Instead, use cache_mode=CacheMode.BYPASS',
        'no_cache_read' : 'Instead, use cache_mode=CacheMode.WRITE_ONLY',
        'no_cache_write' : 'Instead, use cache_mode=CacheMode.READ_ONLY',
    }

    def __init__(
        self,
        # Content Processing Parameters
        word_count_threshold: int = MIN_WORD_THRESHOLD,
        extraction_strategy: ExtractionStrategy = None,
        chunking_strategy: ChunkingStrategy = RegexChunking(),
        markdown_generator: MarkdownGenerationStrategy = DefaultMarkdownGenerator(),
        only_text: bool = False,
        css_selector: str = None,
        target_elements: List[str] = None,
        excluded_tags: list = None,
        excluded_selector: str = None,
        keep_data_attributes: bool = False,
        keep_attrs: list = None,
        remove_forms: bool = False,
        prettiify: bool = False,
        parser_type: str = "lxml",
        scraping_strategy: ContentScrapingStrategy = None,
        proxy_config: Union["ProxyConfig", List["ProxyConfig"], dict, str, None] = None,
        proxy_rotation_strategy: Optional[ProxyRotationStrategy] = None,
        # Sticky Proxy Session Parameters
        proxy_session_id: Optional[str] = None,
        proxy_session_ttl: Optional[int] = None,
        proxy_session_auto_release: bool = False,
        # Browser Location and Identity Parameters
        locale: Optional[str] = None,
        timezone_id: Optional[str] = None,
        geolocation: Optional[GeolocationConfig] = None,
        # SSL Parameters
        fetch_ssl_certificate: bool = False,
        # Caching Parameters
        cache_mode: CacheMode = CacheMode.BYPASS,
        session_id: str = None,
        bypass_cache: bool = False,
        disable_cache: bool = False,
        no_cache_read: bool = False,
        no_cache_write: bool = False,
        shared_data: dict = None,
        # Cache Validation Parameters (Smart Cache)
        check_cache_freshness: bool = False,
        cache_validation_timeout: float = 10.0,
        # Page Navigation and Timing Parameters
        wait_until: str = "domcontentloaded",
        page_timeout: int = PAGE_TIMEOUT,
        wait_for: str = None,
        wait_for_timeout: int = None,
        wait_for_images: bool = False,
        delay_before_return_html: float = 0.1,
        mean_delay: float = 0.1,
        max_range: float = 0.3,
        semaphore_count: int = 5,
        # Page Interaction Parameters
        js_code: Union[str, List[str]] = None,
        js_code_before_wait: Union[str, List[str]] = None,
        c4a_script: Union[str, List[str]] = None,
        js_only: bool = False,
        ignore_body_visibility: bool = True,
        scan_full_page: bool = False,
        scroll_delay: float = 0.2,
        max_scroll_steps: Optional[int] = None,
        process_iframes: bool = False,
        flatten_shadow_dom: bool = False,
        remove_overlay_elements: bool = False,
        remove_consent_popups: bool = False,
        simulate_user: bool = False,
        override_navigator: bool = False,
        magic: bool = False,
        adjust_viewport_to_content: bool = False,
        # Media Handling Parameters
        screenshot: bool = False,
        screenshot_wait_for: float = None,
        screenshot_height_threshold: int = SCREENSHOT_HEIGHT_TRESHOLD,
        force_viewport_screenshot: bool = False,
        pdf: bool = False,
        capture_mhtml: bool = False,
        image_description_min_word_threshold: int = IMAGE_DESCRIPTION_MIN_WORD_THRESHOLD,
        image_score_threshold: int = IMAGE_SCORE_THRESHOLD,
        table_score_threshold: int = 7,
        table_extraction: TableExtractionStrategy = None,
        exclude_external_images: bool = False,
        exclude_all_images: bool = False,
        # Link and Domain Handling Parameters
        exclude_social_media_domains: list = None,
        exclude_external_links: bool = False,
        exclude_social_media_links: bool = False,
        exclude_domains: list = None,
        exclude_internal_links: bool = False,
        score_links: bool = False,
        preserve_https_for_internal_links: bool = False,
        # Debugging and Logging Parameters
        verbose: bool = False,
        log_console: bool = False,
        # Network and Console Capturing Parameters
        capture_network_requests: bool = False,
        capture_console_messages: bool = False,
        # Connection Parameters
        method: str = "GET",
        stream: bool = False,
        prefetch: bool = False,  # When True, return only HTML + links (skip heavy processing)
        process_in_browser: bool = False,  # Force browser processing for raw:/file:// URLs
        url: str = None,
        base_url: str = None,  # Base URL for markdown link resolution (used with raw: HTML)
        check_robots_txt: bool = False,
        user_agent: str = None,
        user_agent_mode: str = None,
        user_agent_generator_config: dict = {},
        # Deep Crawl Parameters
        deep_crawl_strategy: Optional[DeepCrawlStrategy] = None,
        # Link Extraction Parameters
        link_preview_config: Union[LinkPreviewConfig, Dict[str, Any]] = None,
        # Virtual Scroll Parameters
        virtual_scroll_config: Union[VirtualScrollConfig, Dict[str, Any]] = None,
        # URL Matching Parameters
        url_matcher: Optional[UrlMatcher] = None,
        match_mode: MatchMode = MatchMode.OR,
        # Experimental Parameters
        experimental: Dict[str, Any] = None,
        # Anti-Bot Retry Parameters
        max_retries: int = 0,
        fallback_fetch_function: Optional[Callable[[str], Awaitable[str]]] = None,
    ):
        # TODO: Planning to set properties dynamically based on the __init__ signature
        self.url = url
        self.base_url = base_url  # Base URL for markdown link resolution

        # Content Processing Parameters
        self.word_count_threshold = word_count_threshold
        self.extraction_strategy = extraction_strategy
        self.chunking_strategy = chunking_strategy
        self.markdown_generator = markdown_generator
        self.only_text = only_text
        self.css_selector = css_selector
        self.target_elements = target_elements or []
        self.excluded_tags = excluded_tags or []
        self.excluded_selector = excluded_selector or ""
        self.keep_data_attributes = keep_data_attributes
        self.keep_attrs = keep_attrs or []
        self.remove_forms = remove_forms
        self.prettiify = prettiify
        self.parser_type = parser_type
        self.scraping_strategy = scraping_strategy or LXMLWebScrapingStrategy()
        self.proxy_config = proxy_config  # runs through property setter

        self.proxy_rotation_strategy = proxy_rotation_strategy

        # Sticky Proxy Session Parameters
        self.proxy_session_id = proxy_session_id
        self.proxy_session_ttl = proxy_session_ttl
        self.proxy_session_auto_release = proxy_session_auto_release

        # Browser Location and Identity Parameters
        self.locale = locale
        self.timezone_id = timezone_id
        self.geolocation = geolocation

        # SSL Parameters
        self.fetch_ssl_certificate = fetch_ssl_certificate

        # Caching Parameters
        self.cache_mode = cache_mode
        self.session_id = session_id
        self.bypass_cache = bypass_cache
        self.disable_cache = disable_cache
        self.no_cache_read = no_cache_read
        self.no_cache_write = no_cache_write
        self.shared_data = shared_data
        # Cache Validation (Smart Cache)
        self.check_cache_freshness = check_cache_freshness
        self.cache_validation_timeout = cache_validation_timeout

        # Page Navigation and Timing Parameters
        self.wait_until = wait_until
        self.page_timeout = page_timeout
        self.wait_for = wait_for
        self.wait_for_timeout = wait_for_timeout
        self.wait_for_images = wait_for_images
        self.delay_before_return_html = delay_before_return_html
        self.mean_delay = mean_delay
        self.max_range = max_range
        self.semaphore_count = semaphore_count

        # Page Interaction Parameters
        self.js_code = js_code
        self.js_code_before_wait = js_code_before_wait
        self.c4a_script = c4a_script
        self.js_only = js_only
        self.ignore_body_visibility = ignore_body_visibility
        self.scan_full_page = scan_full_page
        self.scroll_delay = scroll_delay
        self.max_scroll_steps = max_scroll_steps
        self.process_iframes = process_iframes
        self.flatten_shadow_dom = flatten_shadow_dom
        self.remove_overlay_elements = remove_overlay_elements
        self.remove_consent_popups = remove_consent_popups
        self.simulate_user = simulate_user
        self.override_navigator = override_navigator
        self.magic = magic
        self.adjust_viewport_to_content = adjust_viewport_to_content

        # Media Handling Parameters
        self.screenshot = screenshot
        self.screenshot_wait_for = screenshot_wait_for
        self.screenshot_height_threshold = screenshot_height_threshold
        self.force_viewport_screenshot = force_viewport_screenshot
        self.pdf = pdf
        self.capture_mhtml = capture_mhtml
        self.image_description_min_word_threshold = image_description_min_word_threshold
        self.image_score_threshold = image_score_threshold
        self.exclude_external_images = exclude_external_images
        self.exclude_all_images = exclude_all_images
        self.table_score_threshold = table_score_threshold
        
        # Table extraction strategy (default to DefaultTableExtraction if not specified)
        if table_extraction is None:
            self.table_extraction = DefaultTableExtraction(table_score_threshold=table_score_threshold)
        else:
            self.table_extraction = table_extraction

        # Link and Domain Handling Parameters
        self.exclude_social_media_domains = (
            exclude_social_media_domains or SOCIAL_MEDIA_DOMAINS
        )
        self.exclude_external_links = exclude_external_links
        self.exclude_social_media_links = exclude_social_media_links
        self.exclude_domains = exclude_domains or []
        self.exclude_internal_links = exclude_internal_links
        self.score_links = score_links
        self.preserve_https_for_internal_links = preserve_https_for_internal_links

        # Debugging and Logging Parameters
        self.verbose = verbose
        self.log_console = log_console
        
        # Network and Console Capturing Parameters
        self.capture_network_requests = capture_network_requests
        self.capture_console_messages = capture_console_messages

        # Connection Parameters
        self.stream = stream
        self.prefetch = prefetch  # Prefetch mode: return only HTML + links
        self.process_in_browser = process_in_browser  # Force browser processing for raw:/file:// URLs
        self.method = method

        # Robots.txt Handling Parameters
        self.check_robots_txt = check_robots_txt

        # User Agent Parameters
        self.user_agent = user_agent
        self.user_agent_mode = user_agent_mode
        self.user_agent_generator_config = user_agent_generator_config

        # Validate type of extraction strategy and chunking strategy if they are provided
        if self.extraction_strategy is not None and not isinstance(
            self.extraction_strategy, ExtractionStrategy
        ):
            raise ValueError(
                "extraction_strategy must be an instance of ExtractionStrategy"
            )
        if self.chunking_strategy is not None and not isinstance(
            self.chunking_strategy, ChunkingStrategy
        ):
            raise ValueError(
                "chunking_strategy must be an instance of ChunkingStrategy"
            )
        if self.markdown_generator is not None and not isinstance(
            self.markdown_generator, MarkdownGenerationStrategy
        ):
            hint = ""
            if isinstance(self.markdown_generator, dict):
                hint = (
                    ' The JSON format must be {"type": "<ClassName>", "params": {...}}.'
                    ' Note: "params" is required — "options" or other keys are not recognized.'
                )
            raise ValueError(
                "markdown_generator must be an instance of MarkdownGenerationStrategy, "
                f"got {type(self.markdown_generator).__name__}.{hint}"
            )

        # Set default chunking strategy if None
        if self.chunking_strategy is None:
            self.chunking_strategy = RegexChunking()

        # Deep Crawl Parameters
        self.deep_crawl_strategy = deep_crawl_strategy
        
        # Link Extraction Parameters
        if link_preview_config is None:
            self.link_preview_config = None
        elif isinstance(link_preview_config, LinkPreviewConfig):
            self.link_preview_config = link_preview_config
        elif isinstance(link_preview_config, dict):
            # Convert dict to config object for backward compatibility
            self.link_preview_config = LinkPreviewConfig.from_dict(link_preview_config)
        else:
            raise ValueError("link_preview_config must be LinkPreviewConfig object or dict")
        
        # Virtual Scroll Parameters
        if virtual_scroll_config is None:
            self.virtual_scroll_config = None
        elif isinstance(virtual_scroll_config, VirtualScrollConfig):
            self.virtual_scroll_config = virtual_scroll_config
        elif isinstance(virtual_scroll_config, dict):
            # Convert dict to config object for backward compatibility
            self.virtual_scroll_config = VirtualScrollConfig.from_dict(virtual_scroll_config)
        else:
            raise ValueError("virtual_scroll_config must be VirtualScrollConfig object or dict")
        
        # URL Matching Parameters
        self.url_matcher = url_matcher
        self.match_mode = match_mode
        
        # Experimental Parameters
        self.experimental = experimental or {}

        # Anti-Bot Retry Parameters
        self.max_retries = max_retries
        self.fallback_fetch_function = fallback_fetch_function

        # Compile C4A scripts if provided
        if self.c4a_script and not self.js_code:
            self._compile_c4a_script()


    @staticmethod
    def _normalize_proxy_config(value):
        """Normalize proxy_config to ProxyConfig, list of ProxyConfig/None, or None."""
        if isinstance(value, list):
            normalized = []
            for p in value:
                if p is None or p == "direct":
                    normalized.append(None)
                elif isinstance(p, dict):
                    normalized.append(ProxyConfig.from_dict(p))
                elif isinstance(p, str):
                    normalized.append(ProxyConfig.from_string(p))
                else:
                    normalized.append(p)
            return normalized
        elif isinstance(value, dict):
            return ProxyConfig.from_dict(value)
        elif isinstance(value, str):
            if value == "direct":
                return None
            return ProxyConfig.from_string(value)
        return value  # ProxyConfig or None

    @property
    def proxy_config(self):
        return self._proxy_config

    @proxy_config.setter
    def proxy_config(self, value):
        self._proxy_config = CrawlerRunConfig._normalize_proxy_config(value)

    def _get_proxy_list(self) -> list:
        """Normalize proxy_config to a list for the retry loop."""
        if self.proxy_config is None:
            return [None]
        if isinstance(self.proxy_config, list):
            return self.proxy_config if self.proxy_config else [None]
        return [self.proxy_config]

    def _compile_c4a_script(self):
        """Compile C4A script to JavaScript"""
        try:
            # Try importing the compiler
            try:
                from .script import compile
            except ImportError:
                from crawl4ai.script import compile
                
            # Handle both string and list inputs
            if isinstance(self.c4a_script, str):
                scripts = [self.c4a_script]
            else:
                scripts = self.c4a_script
                
            # Compile each script
            compiled_js = []
            for i, script in enumerate(scripts):
                result = compile(script)
                
                if result.success:
                    compiled_js.extend(result.js_code)
                else:
                    # Format error message following existing patterns
                    error = result.first_error
                    error_msg = (
                        f"C4A Script compilation error (script {i+1}):\n"
                        f"  Line {error.line}, Column {error.column}: {error.message}\n"
                        f"  Code: {error.source_line}"
                    )
                    if error.suggestions:
                        error_msg += f"\n  Suggestion: {error.suggestions[0].message}"
                        
                    raise ValueError(error_msg)
                    
            self.js_code = compiled_js
            
        except ImportError:
            raise ValueError(
                "C4A script compiler not available. "
                "Please ensure crawl4ai.script module is properly installed."
            )
        except Exception as e:
            # Re-raise with context
            if "compilation error" not in str(e).lower():
                raise ValueError(f"Failed to compile C4A script: {str(e)}")
            raise
    
    def is_match(self, url: str) -> bool:
        """Check if this config matches the given URL.
        
        Args:
            url: The URL to check against this config's matcher
            
        Returns:
            bool: True if this config should be used for the URL or if no matcher is set.
        """
        if self.url_matcher is None:
            return True
            
        if callable(self.url_matcher):
            # Single function matcher
            return self.url_matcher(url)
        
        elif isinstance(self.url_matcher, str):
            # Single pattern string
            from fnmatch import fnmatch
            return fnmatch(url, self.url_matcher)
        
        elif isinstance(self.url_matcher, list):
            # List of mixed matchers
            if not self.url_matcher:  # Empty list
                return False
                
            results = []
            for matcher in self.url_matcher:
                if callable(matcher):
                    results.append(matcher(url))
                elif isinstance(matcher, str):
                    from fnmatch import fnmatch
                    results.append(fnmatch(url, matcher))
                else:
                    # Skip invalid matchers
                    continue
            
            # Apply match mode logic
            if self.match_mode == MatchMode.OR:
                return any(results) if results else False
            else:  # AND mode
                return all(results) if results else False
        
        return False


    def __getattr__(self, name):
        """Handle attribute access."""
        if name in self._UNWANTED_PROPS:
            raise AttributeError(f"Getting '{name}' is deprecated. {self._UNWANTED_PROPS[name]}")
        raise AttributeError(f"'{self.__class__.__name__}' has no attribute '{name}'")

    def __setattr__(self, name, value):
        """Handle attribute setting."""
        # TODO: Planning to set properties dynamically based on the __init__ signature
        sig = inspect.signature(self.__init__)
        all_params = sig.parameters  # Dictionary of parameter names and their details

        if name in self._UNWANTED_PROPS and value is not all_params[name].default:
            raise AttributeError(f"Setting '{name}' is deprecated. {self._UNWANTED_PROPS[name]}")
        
        super().__setattr__(name, value)

    @staticmethod
    def from_kwargs(kwargs: dict) -> "CrawlerRunConfig":
        # Auto-deserialize any dict values that use the {"type": ..., "params": ...}
        # serialization format (e.g. from JSON API requests or dump()/load() roundtrips).
        # This covers markdown_generator, extraction_strategy, content_filter, etc.
        kwargs = {
            k: from_serializable_dict(v) if isinstance(v, dict) and "type" in v else v
            for k, v in kwargs.items()
        }
        # Only pass keys present in kwargs so that __init__ defaults (and
        # set_defaults() overrides) are respected for missing keys.
        valid = inspect.signature(CrawlerRunConfig.__init__).parameters.keys() - {"self"}
        return CrawlerRunConfig(**{k: v for k, v in kwargs.items() if k in valid})

    # Create a funciton returns dict of the object
    def dump(self) -> dict:
        # Serialize the object to a dictionary
        return to_serializable_dict(self)

    @staticmethod
    def load(data: dict) -> "CrawlerRunConfig":
        # Deserialize the object from a dictionary
        config = from_serializable_dict(data)
        if isinstance(config, CrawlerRunConfig):
            return config
        return CrawlerRunConfig.from_kwargs(config)

    def to_dict(self):
        return {
            "word_count_threshold": self.word_count_threshold,
            "extraction_strategy": self.extraction_strategy,
            "chunking_strategy": self.chunking_strategy,
            "markdown_generator": self.markdown_generator,
            "only_text": self.only_text,
            "css_selector": self.css_selector,
            "target_elements": self.target_elements,
            "excluded_tags": self.excluded_tags,
            "excluded_selector": self.excluded_selector,
            "keep_data_attributes": self.keep_data_attributes,
            "keep_attrs": self.keep_attrs,
            "remove_forms": self.remove_forms,
            "prettiify": self.prettiify,
            "parser_type": self.parser_type,
            "scraping_strategy": self.scraping_strategy,
            "proxy_config": (
                [p.to_dict() if hasattr(p, 'to_dict') else p for p in self.proxy_config]
                if isinstance(self.proxy_config, list)
                else (self.proxy_config.to_dict() if hasattr(self.proxy_config, 'to_dict') else self.proxy_config)
            ),
            "proxy_rotation_strategy": self.proxy_rotation_strategy,
            "proxy_session_id": self.proxy_session_id,
            "proxy_session_ttl": self.proxy_session_ttl,
            "proxy_session_auto_release": self.proxy_session_auto_release,
            "locale": self.locale,
            "timezone_id": self.timezone_id,
            "geolocation": self.geolocation,
            "fetch_ssl_certificate": self.fetch_ssl_certificate,
            "cache_mode": self.cache_mode,
            "session_id": self.session_id,
            "bypass_cache": self.bypass_cache,
            "disable_cache": self.disable_cache,
            "no_cache_read": self.no_cache_read,
            "no_cache_write": self.no_cache_write,
            "shared_data": self.shared_data,
            "wait_until": self.wait_until,
            "page_timeout": self.page_timeout,
            "wait_for": self.wait_for,
            "wait_for_timeout": self.wait_for_timeout,
            "wait_for_images": self.wait_for_images,
            "delay_before_return_html": self.delay_before_return_html,
            "mean_delay": self.mean_delay,
            "max_range": self.max_range,
            "semaphore_count": self.semaphore_count,
            "js_code": self.js_code,
            "js_code_before_wait": self.js_code_before_wait,
            "js_only": self.js_only,
            "ignore_body_visibility": self.ignore_body_visibility,
            "scan_full_page": self.scan_full_page,
            "scroll_delay": self.scroll_delay,
            "max_scroll_steps": self.max_scroll_steps,
            "process_iframes": self.process_iframes,
            "flatten_shadow_dom": self.flatten_shadow_dom,
            "remove_overlay_elements": self.remove_overlay_elements,
            "remove_consent_popups": self.remove_consent_popups,
            "simulate_user": self.simulate_user,
            "override_navigator": self.override_navigator,
            "magic": self.magic,
            "adjust_viewport_to_content": self.adjust_viewport_to_content,
            "screenshot": self.screenshot,
            "screenshot_wait_for": self.screenshot_wait_for,
            "screenshot_height_threshold": self.screenshot_height_threshold,
            "pdf": self.pdf,
            "capture_mhtml": self.capture_mhtml,
            "image_description_min_word_threshold": self.image_description_min_word_threshold,
            "image_score_threshold": self.image_score_threshold,
            "table_score_threshold": self.table_score_threshold,
            "table_extraction": self.table_extraction,
            "exclude_all_images": self.exclude_all_images,
            "exclude_external_images": self.exclude_external_images,
            "exclude_social_media_domains": self.exclude_social_media_domains,
            "exclude_external_links": self.exclude_external_links,
            "exclude_social_media_links": self.exclude_social_media_links,
            "exclude_domains": self.exclude_domains,
            "exclude_internal_links": self.exclude_internal_links,
            "score_links": self.score_links,
            "preserve_https_for_internal_links": self.preserve_https_for_internal_links,
            "verbose": self.verbose,
            "log_console": self.log_console,
            "capture_network_requests": self.capture_network_requests,
            "capture_console_messages": self.capture_console_messages,
            "method": self.method,
            "stream": self.stream,
            "prefetch": self.prefetch,
            "process_in_browser": self.process_in_browser,
            "check_robots_txt": self.check_robots_txt,
            "user_agent": self.user_agent,
            "user_agent_mode": self.user_agent_mode,
            "user_agent_generator_config": self.user_agent_generator_config,
            "deep_crawl_strategy": self.deep_crawl_strategy,
            "link_preview_config": self.link_preview_config.to_dict() if self.link_preview_config else None,
            "url": self.url,
            "url_matcher": self.url_matcher,
            "match_mode": self.match_mode,
            "experimental": self.experimental,
            "max_retries": self.max_retries,
        }

    def clone(self, **kwargs):
        """Create a copy of this configuration with updated values.

        Args:
            **kwargs: Key-value pairs of configuration options to update

        Returns:
            CrawlerRunConfig: A new instance with the specified updates

        Example:
            ```python
            # Create a new config with streaming enabled
            stream_config = config.clone(stream=True)

            # Create a new config with multiple updates
            new_config = config.clone(
                stream=True,
                cache_mode=CacheMode.BYPASS,
                verbose=True
            )
            ```
        """
        config_dict = self.to_dict()
        config_dict.update(kwargs)
        return CrawlerRunConfig.from_kwargs(config_dict)

class LLMConfig:
    def __init__(
        self,
        provider: str = DEFAULT_PROVIDER,
        api_token: Optional[str] = None,
        base_url: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        top_p: Optional[float] = None,
        frequency_penalty: Optional[float] = None,
        presence_penalty: Optional[float] = None,
        stop: Optional[List[str]] = None,
        n: Optional[int] = None,
        backoff_base_delay: Optional[int] = None,
        backoff_max_attempts: Optional[int] = None,
        backoff_exponential_factor: Optional[int] = None,
    ):
        """Configuaration class for LLM provider and API token."""
        self.provider = provider
        if api_token and not api_token.startswith("env:"):
            self.api_token = api_token
        elif api_token and api_token.startswith("env:"):
            self.api_token = os.getenv(api_token[4:])
        else:
            # Check if given provider starts with any of key in PROVIDER_MODELS_PREFIXES
            # If not, check if it is in PROVIDER_MODELS
            prefixes = PROVIDER_MODELS_PREFIXES.keys()
            if any(provider.startswith(prefix) for prefix in prefixes):
                selected_prefix = next(
                    (prefix for prefix in prefixes if provider.startswith(prefix)),
                    None,
                )
                self.api_token = PROVIDER_MODELS_PREFIXES.get(selected_prefix)                    
            else:
                self.provider = DEFAULT_PROVIDER
                self.api_token = os.getenv(DEFAULT_PROVIDER_API_KEY)
        self.base_url = base_url
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.top_p = top_p
        self.frequency_penalty = frequency_penalty
        self.presence_penalty = presence_penalty
        self.stop = stop
        self.n = n
        self.backoff_base_delay = backoff_base_delay if backoff_base_delay is not None else 2
        self.backoff_max_attempts = backoff_max_attempts if backoff_max_attempts is not None else 3
        self.backoff_exponential_factor = backoff_exponential_factor if backoff_exponential_factor is not None else 2

    @staticmethod
    def from_kwargs(kwargs: dict) -> "LLMConfig":
        return LLMConfig(
            provider=kwargs.get("provider", DEFAULT_PROVIDER),
            api_token=kwargs.get("api_token"),
            base_url=kwargs.get("base_url"),
            temperature=kwargs.get("temperature"),
            max_tokens=kwargs.get("max_tokens"),
            top_p=kwargs.get("top_p"),
            frequency_penalty=kwargs.get("frequency_penalty"),
            presence_penalty=kwargs.get("presence_penalty"),
            stop=kwargs.get("stop"),
            n=kwargs.get("n"),
            backoff_base_delay=kwargs.get("backoff_base_delay"),
            backoff_max_attempts=kwargs.get("backoff_max_attempts"),
            backoff_exponential_factor=kwargs.get("backoff_exponential_factor")
        )

    def to_dict(self):
        return {
            "provider": self.provider,
            "api_token": self.api_token,
            "base_url": self.base_url,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "top_p": self.top_p,
            "frequency_penalty": self.frequency_penalty,
            "presence_penalty": self.presence_penalty,
            "stop": self.stop,
            "n": self.n,
            "backoff_base_delay": self.backoff_base_delay,
            "backoff_max_attempts": self.backoff_max_attempts,
            "backoff_exponential_factor": self.backoff_exponential_factor
        }

    def clone(self, **kwargs):
        """Create a copy of this configuration with updated values.

        Args:
            **kwargs: Key-value pairs of configuration options to update

        Returns:
            llm_config: A new instance with the specified updates
        """
        config_dict = self.to_dict()
        config_dict.update(kwargs)
        return LLMConfig.from_kwargs(config_dict)

class SeedingConfig:
    """
    Configuration class for URL discovery and pre-validation via AsyncUrlSeeder.
    """
    def __init__(
        self,
        source: str = "sitemap+cc",
        pattern: Optional[str] = "*",
        live_check: bool = False,
        extract_head: bool = False,
        max_urls: int = -1,
        concurrency: int = 1000,
        hits_per_sec: int = 5,
        force: bool = False,
        base_directory: Optional[str] = None,
        llm_config: Optional[LLMConfig] = None,
        verbose: Optional[bool] = None,
        query: Optional[str] = None,
        score_threshold: Optional[float] = None,
        scoring_method: str = "bm25",
        filter_nonsense_urls: bool = True,
        cache_ttl_hours: int = 24,
        validate_sitemap_lastmod: bool = True,
    ):
        """
        Initialize URL seeding configuration.
        
        Args:
            source: Discovery source(s) to use. Options: "sitemap", "cc" (Common Crawl), 
                   or "sitemap+cc" (both). Default: "sitemap+cc"
            pattern: URL pattern to filter discovered URLs (e.g., "*example.com/blog/*"). 
                    Supports glob-style wildcards. Default: "*" (all URLs)
            live_check: Whether to perform HEAD requests to verify URL liveness. 
                       Default: False
            extract_head: Whether to fetch and parse <head> section for metadata extraction.
                         Required for BM25 relevance scoring. Default: False
            max_urls: Maximum number of URLs to discover. Use -1 for no limit. 
                     Default: -1
            concurrency: Maximum concurrent requests for live checks/head extraction. 
                        Default: 1000
            hits_per_sec: Rate limit in requests per second to avoid overwhelming servers. 
                         Default: 5
            force: If True, bypasses the AsyncUrlSeeder's internal .jsonl cache and 
                  re-fetches URLs. Default: False
            base_directory: Base directory for UrlSeeder's cache files (.jsonl). 
                           If None, uses default ~/.crawl4ai/. Default: None
            llm_config: LLM configuration for future features (e.g., semantic scoring). 
                       Currently unused. Default: None
            verbose: Override crawler's general verbose setting for seeding operations. 
                    Default: None (inherits from crawler)
            query: Search query for BM25 relevance scoring (e.g., "python tutorials"). 
                  Requires extract_head=True. Default: None
            score_threshold: Minimum relevance score (0.0-1.0) to include URL. 
                           Only applies when query is provided. Default: None
            scoring_method: Scoring algorithm to use. Currently only "bm25" is supported.
                          Future: "semantic". Default: "bm25"
            filter_nonsense_urls: Filter out utility URLs like robots.txt, sitemap.xml,
                                 ads.txt, favicon.ico, etc. Default: True
            cache_ttl_hours: Hours before sitemap cache expires. Set to 0 to disable TTL
                            (only lastmod validation). Default: 24
            validate_sitemap_lastmod: If True, compares sitemap's <lastmod> with cache
                                     timestamp and refetches if sitemap is newer. Default: True
        """
        self.source = source
        self.pattern = pattern
        self.live_check = live_check
        self.extract_head = extract_head
        self.max_urls = max_urls
        self.concurrency = concurrency
        self.hits_per_sec = hits_per_sec
        self.force = force
        self.base_directory = base_directory
        self.llm_config = llm_config
        self.verbose = verbose
        self.query = query
        self.score_threshold = score_threshold
        self.scoring_method = scoring_method
        self.filter_nonsense_urls = filter_nonsense_urls
        self.cache_ttl_hours = cache_ttl_hours
        self.validate_sitemap_lastmod = validate_sitemap_lastmod

    # Add to_dict, from_kwargs, and clone methods for consistency
    def to_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in self.__dict__.items() if k != 'llm_config' or v is not None}

    @staticmethod
    def from_kwargs(kwargs: Dict[str, Any]) -> 'SeedingConfig':
        return SeedingConfig(**kwargs)

    def clone(self, **kwargs: Any) -> 'SeedingConfig':
        config_dict = self.to_dict()
        config_dict.update(kwargs)
        return SeedingConfig.from_kwargs(config_dict)

```


## File: crawl4ai/async_webcrawler.py


```py
from .__version__ import __version__ as crawl4ai_version
import os
import re
import sys
import time
from pathlib import Path
from typing import Optional, List
import json
import asyncio

# from contextlib import nullcontext, asynccontextmanager
from contextlib import asynccontextmanager
from .models import (
    CrawlResult,
    MarkdownGenerationResult,
    DispatchResult,
    ScrapingResult,
    CrawlResultContainer,
    RunManyReturn
)
from .async_database import async_db_manager
from .chunking_strategy import *  # noqa: F403
from .chunking_strategy import IdentityChunking
from .content_filter_strategy import *  # noqa: F403
from .extraction_strategy import *  # noqa: F403
from .extraction_strategy import NoExtractionStrategy
from .async_crawler_strategy import (
    AsyncCrawlerStrategy,
    AsyncPlaywrightCrawlerStrategy,
    AsyncCrawlResponse,
)
from .cache_context import CacheMode, CacheContext
from .markdown_generation_strategy import (
    DefaultMarkdownGenerator,
    MarkdownGenerationStrategy,
)
from .deep_crawling import DeepCrawlDecorator
from .async_logger import AsyncLogger, AsyncLoggerBase
from .async_configs import BrowserConfig, CrawlerRunConfig, ProxyConfig, SeedingConfig
from .async_dispatcher import *  # noqa: F403
from .async_dispatcher import BaseDispatcher, MemoryAdaptiveDispatcher, RateLimiter
from .async_url_seeder import AsyncUrlSeeder

from .utils import (
    sanitize_input_encode,
    InvalidCSSSelectorError,
    fast_format_html,
    get_error_context,
    RobotsParser,
    preprocess_html_for_schema,
    compute_head_fingerprint,
)
from .cache_validator import CacheValidator, CacheValidationResult
from .antibot_detector import is_blocked


class AsyncWebCrawler:
    """
    Asynchronous web crawler with flexible caching capabilities.

    There are two ways to use the crawler:

    1. Using context manager (recommended for simple cases):
        ```python
        async with AsyncWebCrawler() as crawler:
            result = await crawler.arun(url="https://example.com")
        ```

    2. Using explicit lifecycle management (recommended for long-running applications):
        ```python
        crawler = AsyncWebCrawler()
        await crawler.start()

        # Use the crawler multiple times
        result1 = await crawler.arun(url="https://example.com")
        result2 = await crawler.arun(url="https://another.com")

        await crawler.close()
        ```

    Attributes:
        browser_config (BrowserConfig): Configuration object for browser settings.
        crawler_strategy (AsyncCrawlerStrategy): Strategy for crawling web pages.
        logger (AsyncLogger): Logger instance for recording events and errors.
        crawl4ai_folder (str): Directory for storing cache.
        base_directory (str): Base directory for storing cache.
        ready (bool): Whether the crawler is ready for use.

    Methods:
        start(): Start the crawler explicitly without using context manager.
        close(): Close the crawler explicitly without using context manager.
        arun(): Run the crawler for a single source: URL (web, local file, or raw HTML).
        awarmup(): Perform warmup sequence.
        arun_many(): Run the crawler for multiple sources.
        aprocess_html(): Process HTML content.

    Typical Usage:
        async with AsyncWebCrawler() as crawler:
            result = await crawler.arun(url="https://example.com")
            print(result.markdown)

        Using configuration:
        browser_config = BrowserConfig(browser_type="chromium", headless=True)
        async with AsyncWebCrawler(config=browser_config) as crawler:
            crawler_config = CrawlerRunConfig(
                cache_mode=CacheMode.BYPASS
            )
            result = await crawler.arun(url="https://example.com", config=crawler_config)
            print(result.markdown)
    """

    _domain_last_hit = {}

    def __init__(
        self,
        crawler_strategy: AsyncCrawlerStrategy = None,
        config: BrowserConfig = None,
        base_directory: str = str(
            os.getenv("CRAWL4_AI_BASE_DIRECTORY", Path.home())),
        thread_safe: bool = False,
        logger: AsyncLoggerBase = None,
        **kwargs,
    ):
        """
        Initialize the AsyncWebCrawler.

        Args:
            crawler_strategy: Strategy for crawling web pages. Default AsyncPlaywrightCrawlerStrategy
            config: Configuration object for browser settings. Default BrowserConfig()
            base_directory: Base directory for storing cache
            thread_safe: Whether to use thread-safe operations
            **kwargs: Additional arguments for backwards compatibility
        """
        # Handle browser configuration
        browser_config = config or BrowserConfig()

        self.browser_config = browser_config

        # Initialize logger first since other components may need it
        self.logger = logger or AsyncLogger(
            log_file=os.path.join(base_directory, ".crawl4ai", "crawler.log"),
            verbose=self.browser_config.verbose,
            tag_width=10,
        )

        # Initialize crawler strategy
        params = {k: v for k, v in kwargs.items() if k in [
            "browser_config", "logger"]}
        self.crawler_strategy = crawler_strategy or AsyncPlaywrightCrawlerStrategy(
            browser_config=browser_config,
            logger=self.logger,
            **params,  # Pass remaining kwargs for backwards compatibility
        )

        # Thread safety setup
        self._lock = asyncio.Lock() if thread_safe else None

        # Initialize directories
        self.crawl4ai_folder = os.path.join(base_directory, ".crawl4ai")
        os.makedirs(self.crawl4ai_folder, exist_ok=True)
        os.makedirs(f"{self.crawl4ai_folder}/cache", exist_ok=True)

        # Initialize robots parser
        self.robots_parser = RobotsParser()

        self.ready = False

        # Decorate arun method with deep crawling capabilities
        self._deep_handler = DeepCrawlDecorator(self)
        self.arun = self._deep_handler(self.arun)
        
        self.url_seeder: Optional[AsyncUrlSeeder] = None

    async def start(self):
        """
        Start the crawler explicitly without using context manager.
        This is equivalent to using 'async with' but gives more control over the lifecycle.
        Returns:
            AsyncWebCrawler: The initialized crawler instance
        """
        await self.crawler_strategy.__aenter__()
        self.logger.info(f"Crawl4AI {crawl4ai_version}", tag="INIT")
        self.ready = True
        return self

    async def close(self):
        """
        Close the crawler explicitly without using context manager.
        This should be called when you're done with the crawler if you used start().

        This method will:
        1. Clean up browser resources
        2. Close any open pages and contexts
        """
        await self.crawler_strategy.__aexit__(None, None, None)

    async def __aenter__(self):
        return await self.start()

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    @asynccontextmanager
    async def nullcontext(self):
        """异步空上下文管理器"""
        yield

    async def arun(
        self,
        url: str,
        config: CrawlerRunConfig = None,
        **kwargs,
    ) -> RunManyReturn:
        """
        Runs the crawler for a single source: URL (web, local file, or raw HTML).

        Migration Guide:
        Old way (deprecated):
            result = await crawler.arun(
                url="https://example.com",
                word_count_threshold=200,
                screenshot=True,
                ...
            )

        New way (recommended):
            config = CrawlerRunConfig(
                word_count_threshold=200,
                screenshot=True,
                ...
            )
            result = await crawler.arun(url="https://example.com", config=config)

        Args:
            url: The URL to crawl (http://, https://, file://, or raw:)
            config: Configuration object controlling crawl behavior
            [other parameters maintained for backwards compatibility]

        Returns:
            CrawlResult: The result of crawling and processing
        """
        # Auto-start if not ready
        if not self.ready:
            await self.start()

        config = config or CrawlerRunConfig()
        if not isinstance(url, str) or not url:
            raise ValueError(
                "Invalid URL, make sure the URL is a non-empty string")

        async with self._lock or self.nullcontext():
            try:
                self.logger.verbose = config.verbose

                if config.verbose:
                    import json as _json
                    bc_dict = self.browser_config.to_dict() if hasattr(self.browser_config, 'to_dict') else vars(self.browser_config)
                    cc_dict = config.to_dict() if hasattr(config, 'to_dict') else vars(config)
                    self.logger.info(
                        message="Crawling {url}\n  BrowserConfig: {browser_config}\n  CrawlerRunConfig: {crawler_config}",
                        tag="CRAWL",
                        params={
                            "url": url,
                            "browser_config": _json.dumps({k: str(v) for k, v in bc_dict.items()}, default=str, ensure_ascii=False),
                            "crawler_config": _json.dumps({k: str(v) for k, v in cc_dict.items()}, default=str, ensure_ascii=False),
                        },
                    )

                # Default to ENABLED if no cache mode specified
                if config.cache_mode is None:
                    config.cache_mode = CacheMode.ENABLED

                # Create cache context
                cache_context = CacheContext(url, config.cache_mode, False)

                # Initialize processing variables
                async_response: AsyncCrawlResponse = None
                cached_result: CrawlResult = None
                screenshot_data = None
                pdf_data = None
                extracted_content = None
                start_time = time.perf_counter()

                # Try to get cached result if appropriate
                if cache_context.should_read():
                    cached_result = await async_db_manager.aget_cached_url(url)

                # Smart Cache: Validate cache freshness if enabled
                if cached_result and config.check_cache_freshness:
                    cache_metadata = await async_db_manager.aget_cache_metadata(url)
                    if cache_metadata:
                        async with CacheValidator(timeout=config.cache_validation_timeout) as validator:
                            validation = await validator.validate(
                                url=url,
                                stored_etag=cache_metadata.get("etag"),
                                stored_last_modified=cache_metadata.get("last_modified"),
                                stored_head_fingerprint=cache_metadata.get("head_fingerprint"),
                            )

                        if validation.status == CacheValidationResult.FRESH:
                            cached_result.cache_status = "hit_validated"
                            self.logger.info(
                                message="Cache validated: {reason}",
                                tag="CACHE",
                                params={"reason": validation.reason}
                            )
                            # Update metadata if we got new values
                            if validation.new_etag or validation.new_last_modified:
                                await async_db_manager.aupdate_cache_metadata(
                                    url=url,
                                    etag=validation.new_etag,
                                    last_modified=validation.new_last_modified,
                                    head_fingerprint=validation.new_head_fingerprint,
                                )
                        elif validation.status == CacheValidationResult.ERROR:
                            cached_result.cache_status = "hit_fallback"
                            self.logger.warning(
                                message="Cache validation failed, using cached: {reason}",
                                tag="CACHE",
                                params={"reason": validation.reason}
                            )
                        else:
                            # STALE or UNKNOWN - force recrawl
                            self.logger.info(
                                message="Cache stale: {reason}",
                                tag="CACHE",
                                params={"reason": validation.reason}
                            )
                            cached_result = None
                elif cached_result:
                    cached_result.cache_status = "hit"

                if cached_result:
                    html = sanitize_input_encode(cached_result.html)
                    extracted_content = sanitize_input_encode(
                        cached_result.extracted_content or ""
                    )
                    extracted_content = (
                        None
                        if not extracted_content or extracted_content == "[]"
                        else extracted_content
                    )
                    # If screenshot is requested but its not in cache, then set cache_result to None
                    screenshot_data = cached_result.screenshot
                    pdf_data = cached_result.pdf
                    # if config.screenshot and not screenshot or config.pdf and not pdf:
                    if config.screenshot and not screenshot_data:
                        cached_result = None

                    if config.pdf and not pdf_data:
                        cached_result = None

                    self.logger.url_status(
                        url=cache_context.display_url,
                        success=bool(html),
                        timing=time.perf_counter() - start_time,
                        tag="FETCH",
                    )

                # Update proxy configuration from rotation strategy if available
                if config and config.proxy_rotation_strategy:
                    # Handle sticky sessions - use same proxy for all requests with same session_id
                    if config.proxy_session_id:
                        next_proxy: ProxyConfig = await config.proxy_rotation_strategy.get_proxy_for_session(
                            config.proxy_session_id,
                            ttl=config.proxy_session_ttl
                        )
                        if next_proxy:
                            self.logger.info(
                                message="Using sticky proxy session: {session_id} -> {proxy}",
                                tag="PROXY",
                                params={
                                    "session_id": config.proxy_session_id,
                                    "proxy": next_proxy.server
                                }
                            )
                            config.proxy_config = next_proxy
                    else:
                        # Existing behavior: rotate on each request
                        next_proxy: ProxyConfig = await config.proxy_rotation_strategy.get_next_proxy()
                        if next_proxy:
                            self.logger.info(
                                message="Switch proxy: {proxy}",
                                tag="PROXY",
                                params={"proxy": next_proxy.server}
                            )
                            config.proxy_config = next_proxy

                # Fetch fresh content if needed
                if not cached_result or not html:
                    from urllib.parse import urlparse

                    # Check robots.txt if enabled (once, before any attempts)
                    if config and config.check_robots_txt:
                        if not await self.robots_parser.can_fetch(
                            url, self.browser_config.user_agent
                        ):
                            return CrawlResult(
                                url=url,
                                html="",
                                success=False,
                                status_code=403,
                                error_message="Access denied by robots.txt",
                                response_headers={
                                    "X-Robots-Status": "Blocked by robots.txt"
                                },
                            )

                    # --- Anti-bot retry setup ---
                    # raw: URLs contain caller-provided HTML (e.g. from cache),
                    # not content fetched from a web server.  Anti-bot detection,
                    # proxy retries, and fallback fetching are meaningless here.
                    _is_raw_url = url.startswith("raw:") or url.startswith("raw://")

                    _max_attempts = 1 + getattr(config, "max_retries", 0)
                    _proxy_list = config._get_proxy_list()
                    _original_proxy_config = config.proxy_config
                    _block_reason = ""
                    _done = False
                    crawl_result = None
                    _crawl_stats = {
                        "attempts": 0,
                        "retries": 0,
                        "proxies_used": [],
                        "fallback_fetch_used": False,
                        "resolved_by": None,
                    }

                    for _attempt in range(_max_attempts):
                        if _done:
                            break

                        if _attempt > 0:
                            _crawl_stats["retries"] = _attempt
                            self.logger.warning(
                                message="Anti-bot retry {attempt}/{max_retries} for {url} — {reason}",
                                tag="ANTIBOT",
                                params={
                                    "attempt": _attempt,
                                    "max_retries": config.max_retries,
                                    "url": url[:80],
                                    "reason": _block_reason,
                                },
                            )

                        for _p_idx, _proxy in enumerate(_proxy_list):
                            if _p_idx > 0 or _attempt > 0:
                                self.logger.info(
                                    message="Trying proxy {idx}/{total}: {proxy}",
                                    tag="ANTIBOT",
                                    params={
                                        "idx": _p_idx + 1,
                                        "total": len(_proxy_list),
                                        "proxy": _proxy.server if _proxy else "direct",
                                    },
                                )

                            # Set the active proxy for this attempt
                            config.proxy_config = _proxy
                            _crawl_stats["attempts"] += 1

                            try:
                                t1 = time.perf_counter()

                                if config.user_agent:
                                    self.crawler_strategy.update_user_agent(
                                        config.user_agent)

                                async_response = await self.crawler_strategy.crawl(
                                    url, config=config)

                                html = sanitize_input_encode(async_response.html)
                                screenshot_data = async_response.screenshot
                                pdf_data = async_response.pdf_data
                                js_execution_result = async_response.js_execution_result

                                self.logger.url_status(
                                    url=cache_context.display_url,
                                    success=bool(html),
                                    timing=time.perf_counter() - t1,
                                    tag="FETCH",
                                )

                                crawl_result = await self.aprocess_html(
                                    url=url, html=html,
                                    extracted_content=extracted_content,
                                    config=config,
                                    screenshot_data=screenshot_data,
                                    pdf_data=pdf_data,
                                    verbose=config.verbose,
                                    is_raw_html=True if url.startswith("raw:") else False,
                                    redirected_url=async_response.redirected_url,
                                    original_scheme=urlparse(url).scheme,
                                    **kwargs,
                                )

                                crawl_result.status_code = async_response.status_code
                                is_raw_url = url.startswith("raw:") or url.startswith("raw://")
                                crawl_result.redirected_url = async_response.redirected_url or (None if is_raw_url else url)
                                crawl_result.redirected_status_code = async_response.redirected_status_code
                                crawl_result.response_headers = async_response.response_headers
                                crawl_result.downloaded_files = async_response.downloaded_files
                                crawl_result.js_execution_result = js_execution_result
                                crawl_result.mhtml = async_response.mhtml_data
                                crawl_result.ssl_certificate = async_response.ssl_certificate
                                crawl_result.network_requests = async_response.network_requests
                                crawl_result.console_messages = async_response.console_messages
                                crawl_result.success = bool(html)
                                crawl_result.session_id = getattr(config, "session_id", None)
                                crawl_result.cache_status = "miss"

                                # Check if blocked (skip for raw: URLs —
                                # caller-provided content, anti-bot N/A)
                                if _is_raw_url:
                                    _blocked = False
                                    _block_reason = ""
                                else:
                                    _blocked, _block_reason = is_blocked(
                                        async_response.status_code, html)

                                _crawl_stats["proxies_used"].append({
                                    "proxy": _proxy.server if _proxy else None,
                                    "status_code": async_response.status_code,
                                    "blocked": _blocked,
                                    "reason": _block_reason if _blocked else "",
                                })

                                if not _blocked:
                                    _crawl_stats["resolved_by"] = "proxy" if _proxy else "direct"
                                    _done = True
                                    break  # Success — exit proxy loop

                            except Exception as _crawl_err:
                                _crawl_stats["proxies_used"].append({
                                    "proxy": _proxy.server if _proxy else None,
                                    "status_code": None,
                                    "blocked": True,
                                    "reason": str(_crawl_err),
                                })
                                self.logger.error_status(
                                    url=url,
                                    error=f"Proxy {_proxy.server if _proxy else 'direct'} failed: {_crawl_err}",
                                    tag="ANTIBOT",
                                )
                                _block_reason = str(_crawl_err)
                                # If this is the only proxy and only attempt, re-raise
                                # so the caller gets the real error (not a silent swallow).
                                # But if there are more proxies or retries to try, continue.
                                if len(_proxy_list) <= 1 and _max_attempts <= 1:
                                    raise

                    # Restore original proxy_config
                    config.proxy_config = _original_proxy_config

                    # --- Fallback fetch function (last resort after all retries+proxies exhausted) ---
                    # Invoke fallback when: (a) crawl_result exists but is blocked, OR
                    # (b) crawl_result is None because all proxies threw exceptions (browser crash, timeout).
                    # Skip for raw: URLs — fallback expects a real URL, not raw HTML content.
                    _fallback_fn = getattr(config, "fallback_fetch_function", None)
                    if _fallback_fn and not _done and not _is_raw_url:
                        _needs_fallback = (
                            crawl_result is None  # All proxies threw exceptions
                            or is_blocked(crawl_result.status_code, crawl_result.html or "")[0]
                        )
                        if _needs_fallback:
                            self.logger.warning(
                                message="All retries exhausted, invoking fallback_fetch_function for {url}",
                                tag="ANTIBOT",
                                params={"url": url[:80]},
                            )
                            _crawl_stats["fallback_fetch_used"] = True
                            try:
                                _fallback_html = await _fallback_fn(url)
                                if _fallback_html:
                                    _sanitized_html = sanitize_input_encode(_fallback_html)
                                    try:
                                        crawl_result = await self.aprocess_html(
                                            url=url,
                                            html=_sanitized_html,
                                            extracted_content=extracted_content,
                                            config=config,
                                            screenshot_data=None,
                                            pdf_data=None,
                                            verbose=config.verbose,
                                            is_raw_html=True,
                                            redirected_url=url,
                                            original_scheme=urlparse(url).scheme,
                                            **kwargs,
                                        )
                                    except Exception as _proc_err:
                                        # aprocess_html may fail if browser is dead (e.g.,
                                        # consent popup removal needs Page.evaluate).
                                        # Fall back to a minimal result with raw HTML.
                                        self.logger.warning(
                                            message="Fallback HTML processing failed ({err}), using raw HTML",
                                            tag="ANTIBOT",
                                            params={"err": str(_proc_err)[:100]},
                                        )
                                        crawl_result = CrawlResult(
                                            url=url,
                                            html=_sanitized_html,
                                            success=True,
                                            status_code=200,
                                        )
                                    crawl_result.success = True
                                    crawl_result.status_code = 200
                                    crawl_result.session_id = getattr(config, "session_id", None)
                                    crawl_result.cache_status = "miss"
                                    _crawl_stats["resolved_by"] = "fallback_fetch"
                            except Exception as _fallback_err:
                                self.logger.error_status(
                                    url=url,
                                    error=f"Fallback fetch failed: {_fallback_err}",
                                    tag="ANTIBOT",
                                )

                    # --- Mark blocked results as failed ---
                    # Skip re-check ONLY when fallback SUCCEEDED — the fallback result
                    # is authoritative and real pages may contain anti-bot script markers
                    # (e.g. PerimeterX JS on Walmart) that trigger false positives.
                    # When fallback was attempted but FAILED, we must still re-check
                    # because the result is from a blocked proxy attempt.
                    # Also skip for raw: URLs — caller-provided content, anti-bot N/A.
                    if crawl_result:
                        _fallback_succeeded = _crawl_stats.get("resolved_by") == "fallback_fetch"
                        if not _fallback_succeeded and not _is_raw_url:
                            _blocked, _block_reason = is_blocked(
                                crawl_result.status_code, crawl_result.html or "")
                            if _blocked:
                                if config.verbose:
                                    self.logger.info(
                                        message="Anti-bot blocked: reason={reason}, status={status}, url={url}",
                                        tag="ANTIBOT",
                                        params={"reason": _block_reason, "status": crawl_result.status_code, "url": url[:80]},
                                    )
                                crawl_result.success = False
                                crawl_result.error_message = f"Blocked by anti-bot protection: {_block_reason}"
                        crawl_result.crawl_stats = _crawl_stats
                    else:
                        # All proxies threw exceptions and fallback either wasn't
                        # configured or also failed.  Build a minimal result so the
                        # caller gets crawl_stats instead of None.
                        crawl_result = CrawlResult(
                            url=url,
                            html="",
                            success=False,
                            status_code=None,
                            error_message=f"All proxies failed: {_block_reason}" if _block_reason else "All proxies failed",
                        )
                        crawl_result.crawl_stats = _crawl_stats

                    # Compute head fingerprint for cache validation
                    if crawl_result and crawl_result.html:
                        head_end = crawl_result.html.lower().find('</head>')
                        if head_end != -1:
                            head_html = crawl_result.html[:head_end + 7]
                            crawl_result.head_fingerprint = compute_head_fingerprint(head_html)

                    self.logger.url_status(
                        url=cache_context.display_url,
                        success=crawl_result.success if crawl_result else False,
                        timing=time.perf_counter() - start_time,
                        tag="COMPLETE",
                    )

                    # Update cache if appropriate
                    if cache_context.should_write() and not bool(cached_result):
                        await async_db_manager.acache_url(crawl_result)

                    return CrawlResultContainer(crawl_result)

                else:
                    self.logger.url_status(
                        url=cache_context.display_url,
                        success=True,
                        timing=time.perf_counter() - start_time,
                        tag="COMPLETE"
                    )
                    cached_result.success = bool(html)
                    cached_result.session_id = getattr(
                        config, "session_id", None)
                    # For raw: URLs, don't fall back to the raw HTML string as redirected_url
                    is_raw_url = url.startswith("raw:") or url.startswith("raw://")
                    cached_result.redirected_url = cached_result.redirected_url or (None if is_raw_url else url)
                    return CrawlResultContainer(cached_result)

            except Exception as e:
                error_context = get_error_context(sys.exc_info())

                error_message = (
                    f"Unexpected error in _crawl_web at line {error_context['line_no']} "
                    f"in {error_context['function']} ({error_context['filename']}):\n"
                    f"Error: {str(e)}\n\n"
                    f"Code context:\n{error_context['code_context']}"
                )

                self.logger.error_status(
                    url=url,
                    error=error_message,
                    tag="ERROR",
                )

                return CrawlResultContainer(
                    CrawlResult(
                        url=url, html="", success=False, error_message=error_message
                    )
                )

    async def aprocess_html(
        self,
        url: str,
        html: str,
        extracted_content: str,
        config: CrawlerRunConfig,
        screenshot_data: str,
        pdf_data: str,
        verbose: bool,
        **kwargs,
    ) -> CrawlResult:
        """
        Process HTML content using the provided configuration.

        Args:
            url: The URL being processed
            html: Raw HTML content
            extracted_content: Previously extracted content (if any)
            config: Configuration object controlling processing behavior
            screenshot_data: Screenshot data (if any)
            pdf_data: PDF data (if any)
            verbose: Whether to enable verbose logging
            **kwargs: Additional parameters for backwards compatibility

        Returns:
            CrawlResult: Processed result containing extracted and formatted content
        """
        # === PREFETCH MODE SHORT-CIRCUIT ===
        if getattr(config, 'prefetch', False):
            from .utils import quick_extract_links

            # Use base_url from config (for raw: URLs), redirected_url, or original url
            effective_url = getattr(config, 'base_url', None) or kwargs.get('redirected_url') or url
            links = quick_extract_links(html, effective_url)

            return CrawlResult(
                url=url,
                html=html,
                success=True,
                links=links,
                status_code=kwargs.get('status_code'),
                response_headers=kwargs.get('response_headers'),
                redirected_url=kwargs.get('redirected_url'),
                ssl_certificate=kwargs.get('ssl_certificate'),
                # All other fields default to None
            )
        # === END PREFETCH SHORT-CIRCUIT ===

        cleaned_html = ""
        try:
            _url = url if not kwargs.get("is_raw_html", False) else "Raw HTML"
            t1 = time.perf_counter()

            # Get scraping strategy and ensure it has a logger
            scraping_strategy = config.scraping_strategy
            if not scraping_strategy.logger:
                scraping_strategy.logger = self.logger

            # Process HTML content
            params = config.__dict__.copy()
            params.pop("url", None)
            # add keys from kwargs to params that doesn't exist in params
            params.update({k: v for k, v in kwargs.items()
                          if k not in params.keys()})

            ################################
            # Scraping Strategy Execution  #
            ################################
            result: ScrapingResult = scraping_strategy.scrap(
                url, html, **params)

            if result is None:
                raise ValueError(
                    f"Process HTML, Failed to extract content from the website: {url}"
                )

        except InvalidCSSSelectorError as e:
            raise ValueError(str(e))
        except Exception as e:
            raise ValueError(
                f"Process HTML, Failed to extract content from the website: {url}, error: {str(e)}"
            )

        # Extract results - handle both dict and ScrapingResult
        if isinstance(result, dict):
            cleaned_html = sanitize_input_encode(
                result.get("cleaned_html", ""))
            media = result.get("media", {})
            tables = media.pop("tables", []) if isinstance(media, dict) else []
            links = result.get("links", {})
            metadata = result.get("metadata", {})
        else:
            cleaned_html = sanitize_input_encode(result.cleaned_html)
            # media = result.media.model_dump()
            # tables = media.pop("tables", [])
            # links = result.links.model_dump()
            media = result.media.model_dump() if hasattr(result.media, 'model_dump') else result.media
            tables = media.pop("tables", []) if isinstance(media, dict) else []
            links = result.links.model_dump() if hasattr(result.links, 'model_dump') else result.links
            metadata = result.metadata

        fit_html = preprocess_html_for_schema(html_content=html, text_threshold= 500, max_size= 300_000)

        ################################
        # Generate Markdown            #
        ################################
        markdown_generator: Optional[MarkdownGenerationStrategy] = (
            config.markdown_generator or DefaultMarkdownGenerator()
        )

        # --- SELECT HTML SOURCE BASED ON CONTENT_SOURCE ---
        # Get the desired source from the generator config, default to 'cleaned_html'
        selected_html_source = getattr(markdown_generator, 'content_source', 'cleaned_html')

        # Define the source selection logic using dict dispatch
        html_source_selector = {
            "raw_html": lambda: html,  # The original raw HTML
            "cleaned_html": lambda: cleaned_html,  # The HTML after scraping strategy
            "fit_html": lambda: fit_html,  # The HTML after preprocessing for schema
        }

        markdown_input_html = cleaned_html  # Default to cleaned_html

        try:
            # Get the appropriate lambda function, default to returning cleaned_html if key not found
            source_lambda = html_source_selector.get(selected_html_source, lambda: cleaned_html)
            # Execute the lambda to get the selected HTML
            markdown_input_html = source_lambda()

            # Log which source is being used (optional, but helpful for debugging)
            # if self.logger and verbose:
            #     actual_source_used = selected_html_source if selected_html_source in html_source_selector else 'cleaned_html (default)'
            #     self.logger.debug(f"Using '{actual_source_used}' as source for Markdown generation for {url}", tag="MARKDOWN_SRC")

        except Exception as e:
            # Handle potential errors, especially from preprocess_html_for_schema
            if self.logger:
                self.logger.warning(
                    f"Error getting/processing '{selected_html_source}' for markdown source: {e}. Falling back to cleaned_html.",
                    tag="MARKDOWN_SRC"
                )
            # Ensure markdown_input_html is still the default cleaned_html in case of error
            markdown_input_html = cleaned_html
        # --- END: HTML SOURCE SELECTION ---

        # Uncomment if by default we want to use PruningContentFilter
        # if not config.content_filter and not markdown_generator.content_filter:
        #     markdown_generator.content_filter = PruningContentFilter()

        # Extract <base href> from raw HTML before it gets stripped by cleaning.
        # This ensures relative URLs resolve correctly even with cleaned_html.
        base_url = params.get("base_url") or params.get("redirected_url") or url
        base_tag_match = re.search(r'<base\s[^>]*href\s*=\s*["\']([^"\']+)["\']', html, re.IGNORECASE)
        if base_tag_match:
            base_url = base_tag_match.group(1)

        markdown_result: MarkdownGenerationResult = (
            markdown_generator.generate_markdown(
                input_html=markdown_input_html,
                base_url=base_url
                # html2text_options=kwargs.get('html2text', {})
            )
        )

        # Log processing completion
        self.logger.url_status(
            url=_url,
            success=True,
            timing=int((time.perf_counter() - t1) * 1000) / 1000,
            tag="SCRAPE"
        )
        # self.logger.info(
        #     message="{url:.50}... | Time: {timing}s",
        #     tag="SCRAPE",
        #     params={"url": _url, "timing": int((time.perf_counter() - t1) * 1000) / 1000},
        # )

        ################################
        # Structured Content Extraction           #
        ################################
        if (
            not bool(extracted_content)
            and config.extraction_strategy
            and not isinstance(config.extraction_strategy, NoExtractionStrategy)
        ):
            t1 = time.perf_counter()
            # Choose content based on input_format
            content_format = config.extraction_strategy.input_format
            if content_format == "fit_markdown" and not markdown_result.fit_markdown:

                self.logger.url_status(
                        url=_url,
                        success=bool(html),
                        timing=time.perf_counter() - t1,
                        tag="EXTRACT",
                    )
                content_format = "markdown"

            content = {
                "markdown": markdown_result.raw_markdown,
                "html": html,
                "fit_html": fit_html,
                "cleaned_html": cleaned_html,
                "fit_markdown": markdown_result.fit_markdown,
            }.get(content_format, markdown_result.raw_markdown)

            # Use IdentityChunking for HTML input, otherwise use provided chunking strategy
            chunking = (
                IdentityChunking()
                if content_format in ["html", "cleaned_html", "fit_html"]
                else config.chunking_strategy
            )
            sections = chunking.chunk(content)
            # extracted_content = config.extraction_strategy.run(_url, sections)

            # Use async version if available for better parallelism
            if hasattr(config.extraction_strategy, 'arun'):
                extracted_content = await config.extraction_strategy.arun(_url, sections)
            else:
                # Fallback to sync version run in thread pool to avoid blocking
                extracted_content = await asyncio.to_thread(
                    config.extraction_strategy.run, url, sections
                )
                
            extracted_content = json.dumps(
                extracted_content, indent=4, default=str, ensure_ascii=False
            )

            # Log extraction completion
            self.logger.url_status(
                        url=_url,
                        success=bool(html),
                        timing=time.perf_counter() - t1,
                        tag="EXTRACT",
                    )

        # Apply HTML formatting if requested
        if config.prettiify:
            cleaned_html = fast_format_html(cleaned_html)

        # Return complete crawl result
        return CrawlResult(
            url=url,
            html=html,
            fit_html=fit_html,
            cleaned_html=cleaned_html,
            markdown=markdown_result,
            media=media,
            tables=tables,                       # NEW
            links=links,
            metadata=metadata,
            screenshot=screenshot_data,
            pdf=pdf_data,
            extracted_content=extracted_content,
            success=True,
            error_message="",
        )

    async def arun_many(
        self,
        urls: List[str],
        config: Optional[Union[CrawlerRunConfig, List[CrawlerRunConfig]]] = None,
        dispatcher: Optional[BaseDispatcher] = None,
        # Legacy parameters maintained for backwards compatibility
        # word_count_threshold=MIN_WORD_THRESHOLD,
        # extraction_strategy: ExtractionStrategy = None,
        # chunking_strategy: ChunkingStrategy = RegexChunking(),
        # content_filter: RelevantContentFilter = None,
        # cache_mode: Optional[CacheMode] = None,
        # bypass_cache: bool = False,
        # css_selector: str = None,
        # screenshot: bool = False,
        # pdf: bool = False,
        # user_agent: str = None,
        # verbose=True,
        **kwargs,
    ) -> RunManyReturn:
        """
        Runs the crawler for multiple URLs concurrently using a configurable dispatcher strategy.

        Args:
        urls: List of URLs to crawl
        config: Configuration object(s) controlling crawl behavior. Can be:
            - Single CrawlerRunConfig: Used for all URLs
            - List[CrawlerRunConfig]: Configs with url_matcher for URL-specific settings
        dispatcher: The dispatcher strategy instance to use. Defaults to MemoryAdaptiveDispatcher
        [other parameters maintained for backwards compatibility]

        Returns:
        Union[List[CrawlResult], AsyncGenerator[CrawlResult, None]]:
            Either a list of all results or an async generator yielding results

        Examples:

        # Batch processing (default)
        results = await crawler.arun_many(
            urls=["https://example1.com", "https://example2.com"],
            config=CrawlerRunConfig(cache_mode=CacheMode.BYPASS)
        )
        for result in results:
            print(f"Processed {result.url}: {len(result.markdown)} chars")

        # Streaming results
        async for result in await crawler.arun_many(
            urls=["https://example1.com", "https://example2.com"],
            config=CrawlerRunConfig(cache_mode=CacheMode.BYPASS, stream=True),
        ):
            print(f"Processed {result.url}: {len(result.markdown)} chars")
        """
        config = config or CrawlerRunConfig()

        # When deep_crawl_strategy is set, bypass the dispatcher and call
        # arun() directly for each URL.  The DeepCrawlDecorator on arun()
        # will invoke the strategy and return List[CrawlResult].  The
        # dispatcher cannot handle that return type (it expects a single
        # CrawlResult), so we must handle it here.
        primary_cfg = config[0] if isinstance(config, list) else config
        if getattr(primary_cfg, "deep_crawl_strategy", None):
            if primary_cfg.stream:
                async def _deep_crawl_stream():
                    for url in urls:
                        result = await self.arun(url, config=primary_cfg)
                        if isinstance(result, list):
                            for r in result:
                                yield r
                        else:
                            async for r in result:
                                yield r
                return _deep_crawl_stream()
            else:
                all_results = []
                for url in urls:
                    result = await self.arun(url, config=primary_cfg)
                    if isinstance(result, list):
                        all_results.extend(result)
                    else:
                        all_results.append(result)
                return all_results

        if dispatcher is None:
            primary_cfg = config[0] if isinstance(config, list) else config
            mean_delay = getattr(primary_cfg, "mean_delay", 0.1)
            max_range = getattr(primary_cfg, "max_range", 0.3)
            dispatcher = MemoryAdaptiveDispatcher(
                rate_limiter=RateLimiter(
                    base_delay=(mean_delay, mean_delay + max_range),
                    max_delay=60.0,
                    max_retries=3,
                ),
            )

        def transform_result(task_result):
            return (
                setattr(
                    task_result.result,
                    "dispatch_result",
                    DispatchResult(
                        task_id=task_result.task_id,
                        memory_usage=task_result.memory_usage,
                        peak_memory=task_result.peak_memory,
                        start_time=task_result.start_time,
                        end_time=task_result.end_time,
                        error_message=task_result.error_message,
                    ),
                )
                or task_result.result
            )

        # Handle stream setting - use first config's stream setting if config is a list
        if isinstance(config, list):
            stream = config[0].stream if config else False
            primary_config = config[0] if config else None
        else:
            stream = config.stream
            primary_config = config

        # Helper to release sticky session if auto_release is enabled
        async def maybe_release_session():
            if (primary_config and
                primary_config.proxy_session_id and
                primary_config.proxy_session_auto_release and
                primary_config.proxy_rotation_strategy):
                await primary_config.proxy_rotation_strategy.release_session(
                    primary_config.proxy_session_id
                )
                self.logger.info(
                    message="Auto-released proxy session: {session_id}",
                    tag="PROXY",
                    params={"session_id": primary_config.proxy_session_id}
                )

        if stream:
            async def result_transformer():
                try:
                    async for task_result in dispatcher.run_urls_stream(
                        crawler=self, urls=urls, config=config
                    ):
                        yield transform_result(task_result)
                finally:
                    # Auto-release session after streaming completes
                    await maybe_release_session()

            return result_transformer()
        else:
            try:
                _results = await dispatcher.run_urls(crawler=self, urls=urls, config=config)
                return [transform_result(res) for res in _results]
            finally:
                # Auto-release session after batch completes
                await maybe_release_session()

    async def aseed_urls(
        self,
        domain_or_domains: Union[str, List[str]],
        config: Optional[SeedingConfig] = None,
        **kwargs
    ) -> Union[List[str], Dict[str, List[Union[str, Dict[str, Any]]]]]:
        """
        Discovers, filters, and optionally validates URLs for a given domain(s)
        using sitemaps and Common Crawl archives.

        Args:
            domain_or_domains: A single domain string (e.g., "iana.org") or a list of domains.
            config: A SeedingConfig object to control the seeding process.
                    Parameters passed directly via kwargs will override those in 'config'.
            **kwargs: Additional parameters (e.g., `source`, `live_check`, `extract_head`,
                      `pattern`, `concurrency`, `hits_per_sec`, `force_refresh`, `verbose`)
                      that will be used to construct or update the SeedingConfig.

        Returns:
            If `extract_head` is False:
                - For a single domain: `List[str]` of discovered URLs.
                - For multiple domains: `Dict[str, List[str]]` mapping each domain to its URLs.
            If `extract_head` is True:
                - For a single domain: `List[Dict[str, Any]]` where each dict contains 'url'
                  and 'head_data' (parsed <head> metadata).
                - For multiple domains: `Dict[str, List[Dict[str, Any]]]` mapping each domain
                  to a list of URL data dictionaries.

        Raises:
            ValueError: If `domain_or_domains` is not a string or a list of strings.
            Exception: Any underlying exceptions from AsyncUrlSeeder or network operations.

        Example:
            >>> # Discover URLs from sitemap with live check for 'example.com'
            >>> result = await crawler.aseed_urls("example.com", source="sitemap", live_check=True, hits_per_sec=10)

            >>> # Discover URLs from Common Crawl, extract head data for 'example.com' and 'python.org'
            >>> multi_domain_result = await crawler.aseed_urls(
            >>>     ["example.com", "python.org"],
            >>>     source="cc", extract_head=True, concurrency=200, hits_per_sec=50
            >>> )
        """
        # Initialize AsyncUrlSeeder here if it hasn't been already
        if not self.url_seeder:
            # Pass the crawler's base_directory for seeder's cache management
            # Pass the crawler's logger for consistent logging
            self.url_seeder = AsyncUrlSeeder(
                base_directory=self.crawl4ai_folder,
                logger=self.logger
            )                    

        # Merge config object with direct kwargs, giving kwargs precedence
        seeding_config = config.clone(**kwargs) if config else SeedingConfig.from_kwargs(kwargs)
        
        # Ensure base_directory is set for the seeder's cache
        seeding_config.base_directory = seeding_config.base_directory or self.crawl4ai_folder        
        # Ensure the seeder uses the crawler's logger (if not already set)
        if not self.url_seeder.logger:
            self.url_seeder.logger = self.logger

        # Pass verbose setting if explicitly provided in SeedingConfig or kwargs
        if seeding_config.verbose is not None:
            self.url_seeder.logger.verbose = seeding_config.verbose
        else: # Default to crawler's verbose setting
            self.url_seeder.logger.verbose = self.logger.verbose


        if isinstance(domain_or_domains, str):
            self.logger.info(
                message="Starting URL seeding for domain: {domain}",
                tag="SEED",
                params={"domain": domain_or_domains}
            )
            return await self.url_seeder.urls(
                domain_or_domains,
                seeding_config
            )
        elif isinstance(domain_or_domains, (list, tuple)):
            self.logger.info(
                message="Starting URL seeding for {count} domains",
                tag="SEED",
                params={"count": len(domain_or_domains)}
            )
            # AsyncUrlSeeder.many_urls directly accepts a list of domains and individual params.
            return await self.url_seeder.many_urls(
                domain_or_domains,
                seeding_config
            )
        else:
            raise ValueError("`domain_or_domains` must be a string or a list of strings.")
```


## File: crawl4ai/cli.py


```py
import click
import os
import sys
import time

import humanize
from typing import Dict, Any, Optional, List
import json
import yaml
import anyio
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.prompt import Prompt, Confirm

from crawl4ai import (
    CacheMode,
    AsyncWebCrawler,
    CrawlResult,
    BrowserConfig,
    CrawlerRunConfig,
    LLMExtractionStrategy,
    LXMLWebScrapingStrategy,
    JsonCssExtractionStrategy,
    JsonXPathExtractionStrategy,
    BM25ContentFilter,
    PruningContentFilter,
    BrowserProfiler,
    DefaultMarkdownGenerator,
    LLMConfig,
    BFSDeepCrawlStrategy,
    DFSDeepCrawlStrategy,
    BestFirstCrawlingStrategy,
)
from crawl4ai.browser_profiler import ShrinkLevel, _format_size
from crawl4ai.config import USER_SETTINGS
from crawl4ai.cloud import cloud_cmd
from litellm import completion
from pathlib import Path


# Initialize rich console
console = Console()

def get_global_config() -> dict:
    config_dir = Path.home() / ".crawl4ai"
    config_file = config_dir / "global.yml"
    
    if not config_file.exists():
        config_dir.mkdir(parents=True, exist_ok=True)
        return {}
        
    with open(config_file) as f:
        return yaml.safe_load(f) or {}

def save_global_config(config: dict):
    config_file = Path.home() / ".crawl4ai" / "global.yml"
    with open(config_file, "w", encoding="utf-8") as f:
        yaml.dump(config, f)

def setup_llm_config() -> tuple[str, str]:
    config = get_global_config()
    provider = config.get("DEFAULT_LLM_PROVIDER")
    token = config.get("DEFAULT_LLM_PROVIDER_TOKEN")
    
    if not provider:
        click.echo("\nNo default LLM provider configured.")
        click.echo("Provider format: 'company/model' (e.g., 'openai/gpt-4o', 'anthropic/claude-3-sonnet')")
        click.echo("See available providers at: https://docs.litellm.ai/docs/providers")
        provider = click.prompt("Enter provider")
        
    if not provider.startswith("ollama/"):
        if not token:
            token = click.prompt("Enter API token for " + provider, hide_input=True)
    else:
        token = "no-token"
    
    if not config.get("DEFAULT_LLM_PROVIDER") or not config.get("DEFAULT_LLM_PROVIDER_TOKEN"):
        config["DEFAULT_LLM_PROVIDER"] = provider
        config["DEFAULT_LLM_PROVIDER_TOKEN"] = token
        save_global_config(config)
        click.echo("\nConfiguration saved to ~/.crawl4ai/global.yml")
    
    return provider, token

async def stream_llm_response(url: str, markdown: str, query: str, provider: str, token: str):
    response = completion(
        model=provider,
        api_key=token,
        messages=[
            {
                "content": f"You are Crawl4ai assistant, answering user question based on the provided context which is crawled from {url}.",
                "role": "system"
            },
            {
                "content": f"<|start of context|>\n{markdown}\n<|end of context|>\n\n{query}",
                "role": "user"
            },
        ],
        stream=True,
    )
    
    for chunk in response:
        if content := chunk["choices"][0]["delta"].get("content"):
            print(content, end="", flush=True)
    print()  # New line at end



def parse_key_values(ctx, param, value) -> Dict[str, Any]:
    if not value:
        return {}
    result = {}
    pairs = value.split(',')
    for pair in pairs:
        try:
            k, v = pair.split('=', 1)
            # Handle common value types 
            if v.lower() == 'true': v = True
            elif v.lower() == 'false': v = False
            elif v.isdigit(): v = int(v)
            elif v.replace('.','',1).isdigit(): v = float(v)
            elif v.startswith('[') and v.endswith(']'):
                v = [x.strip() for x in v[1:-1].split(',') if x.strip()]
            elif v.startswith('{') and v.endswith('}'):
                try:
                    v = json.loads(v)
                except json.JSONDecodeError:
                    raise click.BadParameter(f'Invalid JSON object: {v}')
            result[k.strip()] = v
        except ValueError:
            raise click.BadParameter(f'Invalid key=value pair: {pair}')
    return result

def load_config_file(path: Optional[str]) -> dict:
    if not path:
        return {}
    
    try:
        with open(path) as f:
            if path.endswith((".yaml", ".yml")):
                return yaml.safe_load(f)
            return json.load(f)
    except Exception as e:
        raise click.BadParameter(f'Error loading config file {path}: {str(e)}')

def load_schema_file(path: Optional[str]) -> dict:
    if not path:
        return None
    return load_config_file(path)

async def run_crawler(url: str, browser_cfg: BrowserConfig, crawler_cfg: CrawlerRunConfig, verbose: bool):
    if verbose:
        click.echo("Starting crawler with configurations:")
        click.echo(f"Browser config: {browser_cfg.dump()}")
        click.echo(f"Crawler config: {crawler_cfg.dump()}")

    async with AsyncWebCrawler(config=browser_cfg) as crawler:
        try:
            result = await crawler.arun(url=url, config=crawler_cfg)
            return result
        except Exception as e:
            raise click.ClickException(f"Crawling failed: {str(e)}")

def show_examples():
    examples = """
🚀 Crawl4AI CLI Examples

1️⃣  Basic Usage:
    # Simple crawl with default settings
    crwl https://example.com

    # Get markdown output
    crwl https://example.com -o markdown

    # Verbose JSON output with cache bypass
    crwl https://example.com -o json -v --bypass-cache

2️⃣  Using Config Files:
    # Using browser and crawler configs
    crwl https://example.com -B browser.yml -C crawler.yml

    # CSS-based extraction
    crwl https://example.com -e extract_css.yml -s css_schema.json -o json

    # LLM-based extraction with config file
    crwl https://example.com -e extract_llm.yml -s llm_schema.json -o json
    
    # Quick LLM-based JSON extraction (prompts for LLM provider first time)
    crwl https://example.com -j  # Auto-extracts structured data
    crwl https://example.com -j "Extract product details including name, price, and features"  # With specific instructions

3️⃣  Direct Parameters:
    # Browser settings
    crwl https://example.com -b "headless=true,viewport_width=1280,user_agent_mode=random"

    # Crawler settings
    crwl https://example.com -c "css_selector=#main,delay_before_return_html=2,scan_full_page=true"

4️⃣  Profile Management for Identity-Based Crawling:
    # Launch interactive profile manager
    crwl profiles

    # Create, list, and delete browser profiles for identity-based crawling
    # Use a profile for crawling (keeps you logged in)
    crwl https://example.com -p my-profile-name

    # Example: Crawl a site that requires login
    # 1. First create a profile and log in:
    crwl profiles
    # 2. Then use that profile to crawl the authenticated site:
    crwl https://site-requiring-login.com/dashboard -p my-profile-name

5️⃣  CDP Mode for Browser Automation:
    # Launch browser with CDP debugging on default port 9222
    crwl cdp

    # Use a specific profile and custom port
    crwl cdp -p my-profile -P 9223

    # Launch headless browser with CDP enabled
    crwl cdp --headless

    # Launch in incognito mode (ignores profile)
    crwl cdp --incognito

    # Use the CDP URL with other tools (Puppeteer, Playwright, etc.)
    # The URL will be displayed in the terminal when the browser starts

    
6️⃣  Sample Config Files:

browser.yml:
    headless: true
    viewport_width: 1280
    user_agent_mode: "random"
    verbose: true
    ignore_https_errors: true

extract_css.yml:
    type: "json-css"
    params:
        verbose: true

css_schema.json:
    {
      "name": "ArticleExtractor",
      "baseSelector": ".article",
      "fields": [
        {
          "name": "title",
          "selector": "h1.title",
          "type": "text"
        },
        {
          "name": "link",
          "selector": "a.read-more",
          "type": "attribute",
          "attribute": "href"
        }
      ]
    }

extract_llm.yml:
    type: "llm"
    provider: "openai/gpt-4"
    instruction: "Extract all articles with their titles and links"
    api_token: "your-token"
    params:
        temperature: 0.3
        max_tokens: 1000

llm_schema.json:
    {
      "title": "Article",
      "type": "object",
      "properties": {
        "title": {
          "type": "string",
          "description": "The title of the article"
        },
        "link": {
          "type": "string",
          "description": "URL to the full article"
        }
      }
    }

7️⃣  Advanced Usage:
    # Combine configs with direct parameters
    crwl https://example.com -B browser.yml -b "headless=false,viewport_width=1920"

    # Full extraction pipeline with config files
    crwl https://example.com \\
        -B browser.yml \\
        -C crawler.yml \\
        -e extract_llm.yml \\
        -s llm_schema.json \\
        -o json \\
        -v
        
    # Quick LLM-based extraction with specific instructions
    crwl https://amazon.com/dp/B01DFKC2SO \\
        -j "Extract product title, current price, original price, rating, and all product specifications" \\
        -b "headless=true,viewport_width=1280" \\
        -v

    # Content filtering with BM25
    crwl https://example.com \\
        -f filter_bm25.yml \\
        -o markdown-fit

    # Authenticated crawling with profile
    crwl https://login-required-site.com \\
        -p my-authenticated-profile \\
        -c "css_selector=.dashboard-content" \\
        -o markdown

For more documentation visit: https://github.com/unclecode/crawl4ai

8️⃣  Q&A with LLM:
    # Ask a question about the content
    crwl https://example.com -q "What is the main topic discussed?"

    # First view content, then ask questions
    crwl https://example.com -o markdown  # See the crawled content first
    crwl https://example.com -q "Summarize the key points"
    crwl https://example.com -q "What are the conclusions?"

    # Advanced crawling with Q&A
    crwl https://example.com \\
        -B browser.yml \\
        -c "css_selector=article,scan_full_page=true" \\
        -q "What are the pros and cons mentioned?"

    Note: First time using -q will prompt for LLM provider and API token.
    These will be saved in ~/.crawl4ai/global.yml for future use.
    
    Supported provider format: 'company/model'
    Examples:
      - ollama/llama3.3
      - openai/gpt-4
      - anthropic/claude-3-sonnet
      - cohere/command
      - google/gemini-pro
    
    See full list of providers: https://docs.litellm.ai/docs/providers
    
    # Set default LLM provider and token in advance
    crwl config set DEFAULT_LLM_PROVIDER "anthropic/claude-3-sonnet"
    crwl config set DEFAULT_LLM_PROVIDER_TOKEN "your-api-token-here"
    
    # Set default browser behavior
    crwl config set BROWSER_HEADLESS false  # Always show browser window
    crwl config set USER_AGENT_MODE random  # Use random user agent

9️⃣ Profile Management:
    # Launch interactive profile manager
    crwl profiles

    # Create a profile and use it for crawling
    crwl profiles  # Create and set up your profile interactively
    crwl https://example.com -p my-profile-name  # Use profile for crawling

    # Example workflow for authenticated site
    # 1. First create a profile and log in to the site:
    crwl profiles  # Select "Create new profile" option
    # 2. Then use that profile to crawl authenticated content:
    crwl https://site-requiring-login.com/dashboard -p my-profile-name

🔄 Builtin Browser Management:
    # Start a builtin browser (runs in the background)
    crwl browser start
    
    # Check builtin browser status
    crwl browser status
    
    # Open a visible window to see the browser
    crwl browser view --url https://example.com
    
    # Stop the builtin browser
    crwl browser stop
    
    # Restart with different options
    crwl browser restart --browser-type chromium --port 9223 --no-headless
    
    # Use the builtin browser in your code
    # (Just set browser_mode="builtin" in your BrowserConfig)
    browser_config = BrowserConfig(
        browser_mode="builtin", 
        headless=True
    )
    
    # Usage via CLI:
    crwl https://example.com -b "browser_mode=builtin"
"""
    click.echo(examples)

def get_directory_size(path: str) -> int:
    """Calculate the total size of a directory in bytes"""
    total_size = 0
    for dirpath, _, filenames in os.walk(path):
        for f in filenames:
            fp = os.path.join(dirpath, f)
            if not os.path.islink(fp):
                total_size += os.path.getsize(fp)
    return total_size

def display_profiles_table(profiles: List[Dict[str, Any]]):
    """Display a rich table of browser profiles"""
    if not profiles:
        console.print(Panel("[yellow]No profiles found. Create one with the 'create' command.[/yellow]", 
                          title="Browser Profiles", border_style="blue"))
        return
    
    table = Table(title="Browser Profiles", show_header=True, header_style="bold cyan", border_style="blue")
    table.add_column("#", style="dim", width=4)
    table.add_column("Name", style="cyan", no_wrap=True)
    table.add_column("Path", style="green")
    table.add_column("Created", style="yellow")
    table.add_column("Browser", style="magenta")
    table.add_column("Size", style="blue", justify="right")
    
    for i, profile in enumerate(profiles):
        # Calculate folder size
        size = get_directory_size(profile["path"])
        human_size = humanize.naturalsize(size)
        
        # Format creation date
        created = profile["created"].strftime("%Y-%m-%d %H:%M")
        
        # Add row to table
        table.add_row(
            str(i+1), 
            profile["name"], 
            profile["path"], 
            created, 
            profile["type"].capitalize(), 
            human_size
        )
    
    console.print(table)

async def create_profile_interactive(profiler: BrowserProfiler):
    """Interactive profile creation wizard"""
    console.print(Panel("[bold cyan]Create Browser Profile[/bold cyan]\n"
                      "This will open a browser window for you to set up your identity.\n"
                      "Log in to sites, adjust settings, then press 'q' to save.",
                      border_style="cyan"))
    
    profile_name = Prompt.ask("[cyan]Enter profile name[/cyan]", default=f"profile_{int(time.time())}")
    
    console.print("[cyan]Creating profile...[/cyan]")
    console.print("[yellow]A browser window will open. After logging in to sites, press 'q' in this terminal to save.[/yellow]")
    
    # Create the profile
    try:
        profile_path = await profiler.create_profile(profile_name)
        
        if profile_path:
            console.print(f"[green]Profile successfully created at:[/green] {profile_path}")
        else:
            console.print("[red]Failed to create profile.[/red]")
    except Exception as e:
        console.print(f"[red]Error creating profile: {str(e)}[/red]")

def delete_profile_interactive(profiler: BrowserProfiler):
    """Interactive profile deletion"""
    profiles = profiler.list_profiles()
    
    if not profiles:
        console.print("[yellow]No profiles found to delete.[/yellow]")
        return
    
    # Display profiles
    display_profiles_table(profiles)
    
    # Get profile selection
    idx = Prompt.ask(
        "[red]Enter number of profile to delete[/red]", 
        console=console,
        choices=[str(i+1) for i in range(len(profiles))],
        show_choices=False
    )
    
    try:
        idx = int(idx) - 1
        profile = profiles[idx]
        
        # Confirm deletion
        if Confirm.ask(f"[red]Are you sure you want to delete profile '{profile['name']}'?[/red]"):
            success = profiler.delete_profile(profile["path"])
            
            if success:
                console.print(f"[green]Profile '{profile['name']}' deleted successfully.[/green]")
            else:
                console.print(f"[red]Failed to delete profile '{profile['name']}'.[/red]")
    except (ValueError, IndexError):
        console.print("[red]Invalid selection.[/red]")
        
async def crawl_with_profile_cli(profile_path, url):
    """Use a profile to crawl a website via CLI"""
    console.print(f"[cyan]Crawling [bold]{url}[/bold] using profile at [bold]{profile_path}[/bold][/cyan]")
    
    # Create browser config with the profile
    browser_cfg = BrowserConfig(
        headless=False,  # Set to False to see the browser in action
        use_managed_browser=True,
        user_data_dir=profile_path
    )
    
    # Default crawler config
    crawler_cfg = CrawlerRunConfig()
    
    # Ask for output format
    output_format = Prompt.ask(
        "[cyan]Output format[/cyan]",
        choices=["all", "json", "markdown", "md", "title"],
        default="markdown"
    )
    
    try:
        # Run the crawler
        result = await run_crawler(url, browser_cfg, crawler_cfg, True)
        
        # Get JSON output config
        config = get_global_config()
        ensure_ascii = config.get("JSON_ENSURE_ASCII", USER_SETTINGS["JSON_ENSURE_ASCII"]["default"])

        # Handle output
        if output_format == "all":
            console.print(json.dumps(result.model_dump(), indent=2, ensure_ascii=ensure_ascii))
        elif output_format == "json":
            console.print(json.dumps(json.loads(result.extracted_content), indent=2, ensure_ascii=ensure_ascii))
        elif output_format in ["markdown", "md"]:
            console.print(result.markdown.raw_markdown)
        elif output_format == "title":
            console.print(result.metadata.get("title", "No title found"))
        
        console.print(f"[green]Successfully crawled[/green] {url}")
        return result
    except Exception as e:
        console.print(f"[red]Error crawling:[/red] {str(e)}")
        return None
        
async def use_profile_to_crawl():
    """Interactive profile selection for crawling"""
    profiler = BrowserProfiler()
    profiles = profiler.list_profiles()
    
    if not profiles:
        console.print("[yellow]No profiles found. Create one first.[/yellow]")
        return
        
    # Display profiles
    display_profiles_table(profiles)
    
    # Get profile selection
    idx = Prompt.ask(
        "[cyan]Enter number of profile to use[/cyan]", 
        console=console,
        choices=[str(i+1) for i in range(len(profiles))],
        show_choices=False
    )
    
    try:
        idx = int(idx) - 1
        profile = profiles[idx]
        
        # Get URL
        url = Prompt.ask("[cyan]Enter URL to crawl[/cyan]")
        if url:
            # Crawl with the selected profile
            await crawl_with_profile_cli(profile["path"], url)
        else:
            console.print("[red]No URL provided[/red]")
    except (ValueError, IndexError):
        console.print("[red]Invalid selection[/red]")

async def manage_profiles():
    """Interactive profile management menu"""
    profiler = BrowserProfiler()
    
    options = {
        "1": "List profiles",
        "2": "Create new profile",
        "3": "Delete profile",
        "4": "Use a profile to crawl a website",
        "5": "Exit",
    }
    
    while True:
        console.print(Panel("[bold cyan]Browser Profile Manager[/bold cyan]", border_style="cyan"))
        
        for key, value in options.items():
            color = "green" if key == "1" else "yellow" if key == "2" else "red" if key == "3" else "blue" if key == "4" else "cyan"
            console.print(f"[{color}]{key}[/{color}]. {value}")
        
        choice = Prompt.ask("Enter choice", choices=list(options.keys()), default="1")
        
        if choice == "1":
            # List profiles
            profiles = profiler.list_profiles()
            display_profiles_table(profiles)
        
        elif choice == "2":
            # Create profile
            await create_profile_interactive(profiler)
        
        elif choice == "3":
            # Delete profile
            delete_profile_interactive(profiler)
            
        elif choice == "4":
            # Use profile to crawl
            await use_profile_to_crawl()
        
        elif choice == "5":
            # Exit
            console.print("[cyan]Exiting profile manager.[/cyan]")
            break
        
        # Add a separator between operations
        console.print("\n")



@click.group(context_settings={"help_option_names": ["-h", "--help"]})
def cli():
    """Crawl4AI CLI - Web content extraction and browser profile management tool"""
    pass

# Add cloud command group
cli.add_command(cloud_cmd)


@cli.group("browser")
def browser_cmd():
    """Manage browser instances for Crawl4AI
    
    Commands to manage browser instances for Crawl4AI, including:
    - status - Check status of the builtin browser
    - start - Start a new builtin browser
    - stop - Stop the running builtin browser
    - restart - Restart the builtin browser
    """
    pass
    
@browser_cmd.command("status")
def browser_status_cmd():
    """Show status of the builtin browser"""
    profiler = BrowserProfiler()
    
    try:
        status = anyio.run(profiler.get_builtin_browser_status)
        
        if status["running"]:
            info = status["info"]
            console.print(Panel(
                f"[green]Builtin browser is running[/green]\n\n"
                f"CDP URL: [cyan]{info['cdp_url']}[/cyan]\n"
                f"Process ID: [yellow]{info['pid']}[/yellow]\n"
                f"Browser type: [blue]{info['browser_type']}[/blue]\n"
                f"User data directory: [magenta]{info['user_data_dir']}[/magenta]\n"
                f"Started: [cyan]{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(info['start_time']))}[/cyan]",
                title="Builtin Browser Status",
                border_style="green"
            ))
        else:
            console.print(Panel(
                "[yellow]Builtin browser is not running[/yellow]\n\n"
                "Use 'crwl browser start' to start a builtin browser",
                title="Builtin Browser Status",
                border_style="yellow"
            ))
            
    except Exception as e:
        console.print(f"[red]Error checking browser status: {str(e)}[/red]")
        sys.exit(1)
        
@browser_cmd.command("start")
@click.option("--browser-type", "-b", type=click.Choice(["chromium", "firefox"]), default="chromium", 
              help="Browser type (default: chromium)")
@click.option("--port", "-p", type=int, default=9222, help="Debugging port (default: 9222)")
@click.option("--headless/--no-headless", default=True, help="Run browser in headless mode")
def browser_start_cmd(browser_type: str, port: int, headless: bool):
    """Start a builtin browser instance
    
    This will start a persistent browser instance that can be used by Crawl4AI
    by setting browser_mode="builtin" in BrowserConfig.
    """
    profiler = BrowserProfiler()
    
    # First check if browser is already running
    status = anyio.run(profiler.get_builtin_browser_status)
    if status["running"]:
        console.print(Panel(
            "[yellow]Builtin browser is already running[/yellow]\n\n"
            f"CDP URL: [cyan]{status['cdp_url']}[/cyan]\n\n"
            "Use 'crwl browser restart' to restart the browser",
            title="Builtin Browser Start",
            border_style="yellow"
        ))
        return
    
    try:
        console.print(Panel(
            f"[cyan]Starting builtin browser[/cyan]\n\n"
            f"Browser type: [green]{browser_type}[/green]\n"
            f"Debugging port: [yellow]{port}[/yellow]\n"
            f"Headless: [cyan]{'Yes' if headless else 'No'}[/cyan]",
            title="Builtin Browser Start",
            border_style="cyan"
        ))
        
        cdp_url = anyio.run(
            profiler.launch_builtin_browser,
            browser_type,
            port,
            headless
        )
        
        if cdp_url:
            console.print(Panel(
                f"[green]Builtin browser started successfully[/green]\n\n"
                f"CDP URL: [cyan]{cdp_url}[/cyan]\n\n"
                "This browser will be used automatically when setting browser_mode='builtin'",
                title="Builtin Browser Start",
                border_style="green"
            ))
        else:
            console.print(Panel(
                "[red]Failed to start builtin browser[/red]",
                title="Builtin Browser Start",
                border_style="red"
            ))
            sys.exit(1)
            
    except Exception as e:
        console.print(f"[red]Error starting builtin browser: {str(e)}[/red]")
        sys.exit(1)
        
@browser_cmd.command("stop")
def browser_stop_cmd():
    """Stop the running builtin browser"""
    profiler = BrowserProfiler()
    
    try:
        # First check if browser is running
        status = anyio.run(profiler.get_builtin_browser_status)
        if not status["running"]:
            console.print(Panel(
                "[yellow]No builtin browser is currently running[/yellow]",
                title="Builtin Browser Stop",
                border_style="yellow"
            ))
            return
            
        console.print(Panel(
            "[cyan]Stopping builtin browser...[/cyan]",
            title="Builtin Browser Stop", 
            border_style="cyan"
        ))
        
        success = anyio.run(profiler.kill_builtin_browser)
        
        if success:
            console.print(Panel(
                "[green]Builtin browser stopped successfully[/green]",
                title="Builtin Browser Stop",
                border_style="green"
            ))
        else:
            console.print(Panel(
                "[red]Failed to stop builtin browser[/red]",
                title="Builtin Browser Stop",
                border_style="red"
            ))
            sys.exit(1)
            
    except Exception as e:
        console.print(f"[red]Error stopping builtin browser: {str(e)}[/red]")
        sys.exit(1)
        
@browser_cmd.command("view")
@click.option("--url", "-u", help="URL to navigate to (defaults to about:blank)")
def browser_view_cmd(url: Optional[str]):
    """
    Open a visible window of the builtin browser
    
    This command connects to the running builtin browser and opens a visible window,
    allowing you to see what the browser is currently viewing or navigate to a URL.
    """
    profiler = BrowserProfiler()
    
    try:
        # First check if browser is running
        status = anyio.run(profiler.get_builtin_browser_status)
        if not status["running"]:
            console.print(Panel(
                "[yellow]No builtin browser is currently running[/yellow]\n\n"
                "Use 'crwl browser start' to start a builtin browser first",
                title="Builtin Browser View",
                border_style="yellow"
            ))
            return
        
        info = status["info"]
        cdp_url = info["cdp_url"]
        
        console.print(Panel(
            f"[cyan]Opening visible window connected to builtin browser[/cyan]\n\n"
            f"CDP URL: [green]{cdp_url}[/green]\n"
            f"URL to load: [yellow]{url or 'about:blank'}[/yellow]",
            title="Builtin Browser View",
            border_style="cyan"
        ))
        
        # Use the CDP URL to launch a new visible window
        import subprocess
        import os
        
        # Determine the browser command based on platform
        if sys.platform == "darwin":  # macOS
            browser_cmd = ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"]
        elif sys.platform == "win32":  # Windows
            browser_cmd = ["C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe"]
        else:  # Linux
            browser_cmd = ["google-chrome"]
        
        # Add arguments
        browser_args = [
            f"--remote-debugging-port={info['debugging_port']}",
            "--remote-debugging-address=localhost",
            "--no-first-run",
            "--no-default-browser-check"
        ]
        
        # Add URL if provided
        if url:
            browser_args.append(url)
        
        # Launch browser
        try:
            subprocess.Popen(browser_cmd + browser_args)
            console.print("[green]Browser window opened. Close it when finished viewing.[/green]")
        except Exception as e:
            console.print(f"[red]Error launching browser: {str(e)}[/red]")
            console.print(f"[yellow]Try connecting manually to {cdp_url} in Chrome or using the '--remote-debugging-port' flag.[/yellow]")
    
    except Exception as e:
        console.print(f"[red]Error viewing builtin browser: {str(e)}[/red]")
        sys.exit(1)

@browser_cmd.command("restart")
@click.option("--browser-type", "-b", type=click.Choice(["chromium", "firefox"]), default=None, 
              help="Browser type (defaults to same as current)")
@click.option("--port", "-p", type=int, default=None, help="Debugging port (defaults to same as current)")
@click.option("--headless/--no-headless", default=None, help="Run browser in headless mode")
def browser_restart_cmd(browser_type: Optional[str], port: Optional[int], headless: Optional[bool]):
    """Restart the builtin browser
    
    Stops the current builtin browser if running and starts a new one.
    By default, uses the same configuration as the current browser.
    """
    profiler = BrowserProfiler()
    
    try:
        # First check if browser is running and get its config
        status = anyio.run(profiler.get_builtin_browser_status)
        current_config = {}
        
        if status["running"]:
            info = status["info"]
            current_config = {
                "browser_type": info["browser_type"],
                "port": info["debugging_port"],
                "headless": True  # Default assumption
            }
            
            # Stop the browser
            console.print(Panel(
                "[cyan]Stopping current builtin browser...[/cyan]",
                title="Builtin Browser Restart", 
                border_style="cyan"
            ))
            
            success = anyio.run(profiler.kill_builtin_browser)
            if not success:
                console.print(Panel(
                    "[red]Failed to stop current browser[/red]",
                    title="Builtin Browser Restart",
                    border_style="red"
                ))
                sys.exit(1)
        
        # Use provided options or defaults from current config
        browser_type = browser_type or current_config.get("browser_type", "chromium")
        port = port or current_config.get("port", 9222)
        headless = headless if headless is not None else current_config.get("headless", True)
        
        # Start a new browser
        console.print(Panel(
            f"[cyan]Starting new builtin browser[/cyan]\n\n"
            f"Browser type: [green]{browser_type}[/green]\n"
            f"Debugging port: [yellow]{port}[/yellow]\n"
            f"Headless: [cyan]{'Yes' if headless else 'No'}[/cyan]",
            title="Builtin Browser Restart",
            border_style="cyan"
        ))
        
        cdp_url = anyio.run(
            profiler.launch_builtin_browser,
            browser_type,
            port,
            headless
        )
        
        if cdp_url:
            console.print(Panel(
                f"[green]Builtin browser restarted successfully[/green]\n\n"
                f"CDP URL: [cyan]{cdp_url}[/cyan]",
                title="Builtin Browser Restart",
                border_style="green"
            ))
        else:
            console.print(Panel(
                "[red]Failed to restart builtin browser[/red]",
                title="Builtin Browser Restart",
                border_style="red"
            ))
            sys.exit(1)
            
    except Exception as e:
        console.print(f"[red]Error restarting builtin browser: {str(e)}[/red]")
        sys.exit(1)

@cli.command("cdp")
@click.option("--user-data-dir", "-d", help="Directory to use for browser data (will be created if it doesn't exist)")
@click.option("--port", "-P", type=int, default=9222, help="Debugging port (default: 9222)")
@click.option("--browser-type", "-b", type=click.Choice(["chromium", "firefox"]), default="chromium", 
              help="Browser type (default: chromium)")
@click.option("--headless", is_flag=True, help="Run browser in headless mode")
@click.option("--incognito", is_flag=True, help="Run in incognito/private mode (ignores user-data-dir)")
def cdp_cmd(user_data_dir: Optional[str], port: int, browser_type: str, headless: bool, incognito: bool):
    """Launch a standalone browser with CDP debugging enabled
    
    This command launches a browser with Chrome DevTools Protocol (CDP) debugging enabled,
    prints the CDP URL, and keeps the browser running until you press 'q'.
    
    The CDP URL can be used for various automation and debugging tasks.
    
    Examples:
        # Launch Chromium with CDP on default port 9222
        crwl cdp
        
        # Use a specific directory for browser data and custom port
        crwl cdp --user-data-dir ~/browser-data --port 9223
        
        # Launch in headless mode
        crwl cdp --headless
        
        # Launch in incognito mode (ignores user-data-dir)
        crwl cdp --incognito
    """
    profiler = BrowserProfiler()
    
    try:
        # Handle data directory
        data_dir = None
        if not incognito and user_data_dir:
            # Expand user path (~/something)
            expanded_path = os.path.expanduser(user_data_dir)
            
            # Create directory if it doesn't exist
            if not os.path.exists(expanded_path):
                console.print(f"[yellow]Directory '{expanded_path}' doesn't exist. Creating it.[/yellow]")
                os.makedirs(expanded_path, exist_ok=True)
            
            data_dir = expanded_path
        
        # Print launch info
        console.print(Panel(
            f"[cyan]Launching browser with CDP debugging[/cyan]\n\n"
            f"Browser type: [green]{browser_type}[/green]\n"
            f"Debugging port: [yellow]{port}[/yellow]\n"
            f"User data directory: [cyan]{data_dir or 'Temporary directory'}[/cyan]\n"
            f"Headless: [cyan]{'Yes' if headless else 'No'}[/cyan]\n"
            f"Incognito: [cyan]{'Yes' if incognito else 'No'}[/cyan]\n\n"
            f"[yellow]Press 'q' to quit when done[/yellow]",
            title="CDP Browser",
            border_style="cyan"
        ))
        
        # Run the browser
        cdp_url = anyio.run(
            profiler.launch_standalone_browser,
            browser_type,
            data_dir,
            port,
            headless
        )
        
        if not cdp_url:
            console.print("[red]Failed to launch browser or get CDP URL[/red]")
            sys.exit(1)
            
    except Exception as e:
        console.print(f"[red]Error launching CDP browser: {str(e)}[/red]")
        sys.exit(1)


@cli.command("crawl")
@click.argument("url", required=True)
@click.option("--browser-config", "-B", type=click.Path(exists=True), help="Browser config file (YAML/JSON)")
@click.option("--crawler-config", "-C", type=click.Path(exists=True), help="Crawler config file (YAML/JSON)")
@click.option("--filter-config", "-f", type=click.Path(exists=True), help="Content filter config file")
@click.option("--extraction-config", "-e", type=click.Path(exists=True), help="Extraction strategy config file")
@click.option("--json-extract", "-j", is_flag=False, flag_value="", default=None, help="Extract structured data using LLM with optional description")
@click.option("--schema", "-s", type=click.Path(exists=True), help="JSON schema for extraction")
@click.option("--browser", "-b", type=str, callback=parse_key_values, help="Browser parameters as key1=value1,key2=value2")
@click.option("--crawler", "-c", type=str, callback=parse_key_values, help="Crawler parameters as key1=value1,key2=value2")
@click.option("--output", "-o", type=click.Choice(["all", "json", "markdown", "md", "markdown-fit", "md-fit"]), default="all")
@click.option("--output-file", "-O", type=click.Path(), help="Output file path (default: stdout)")
@click.option("--bypass-cache", "-bc", is_flag=True, default=True, help="Bypass cache when crawling")
@click.option("--question", "-q", help="Ask a question about the crawled content")
@click.option("--verbose", "-v", is_flag=True)
@click.option("--profile", "-p", help="Use a specific browser profile (by name)")
@click.option("--deep-crawl", type=click.Choice(["bfs", "dfs", "best-first"]), help="Enable deep crawling with specified strategy (bfs, dfs, or best-first)")
@click.option("--max-pages", type=int, default=10, help="Maximum number of pages to crawl in deep crawl mode")
@click.option("--json-ensure-ascii/--no-json-ensure-ascii", default=None, help="Escape non-ASCII characters in JSON output (default: from global config)")
def crawl_cmd(url: str, browser_config: str, crawler_config: str, filter_config: str,
           extraction_config: str, json_extract: str, schema: str, browser: Dict, crawler: Dict,
           output: str, output_file: str, bypass_cache: bool, question: str, verbose: bool, profile: str, deep_crawl: str, max_pages: int, json_ensure_ascii: Optional[bool]):
    """Crawl a website and extract content

    Simple Usage:
        crwl crawl https://example.com
    """
    
    # Handle profile option
    if profile:
        profiler = BrowserProfiler()
        profile_path = profiler.get_profile_path(profile)
        
        if not profile_path:
            profiles = profiler.list_profiles()
            
            if profiles:
                console.print(f"[red]Profile '{profile}' not found. Available profiles:[/red]")
                display_profiles_table(profiles)
            else:
                console.print("[red]No profiles found. Create one with 'crwl profiles'[/red]")
            
            return
        
        # Include the profile in browser config
        if not browser:
            browser = {}
        browser["user_data_dir"] = profile_path
        browser["use_managed_browser"] = True
        
        if verbose:
            console.print(f"[green]Using browser profile:[/green] {profile}")
            
    try:
        # Load base configurations
        browser_cfg = BrowserConfig.load(load_config_file(browser_config))
        crawler_cfg = CrawlerRunConfig.load(load_config_file(crawler_config))
        
        # Override with CLI params
        if browser:
            browser_cfg = browser_cfg.clone(**browser)
        if crawler:
            crawler_cfg = crawler_cfg.clone(**crawler)
            
        # Handle content filter config
        if filter_config or output in ["markdown-fit", "md-fit"]:
            if filter_config:
                filter_conf = load_config_file(filter_config)
            elif not filter_config and output in ["markdown-fit", "md-fit"]:
                filter_conf = {
                    "type": "pruning",
                    "query": "",
                    "threshold": 0.48
                }
            if filter_conf["type"] == "bm25":
                crawler_cfg.markdown_generator = DefaultMarkdownGenerator(
                    content_filter = BM25ContentFilter(
                        user_query=filter_conf.get("query"),
                        bm25_threshold=filter_conf.get("threshold", 1.0),
                        use_stemming=filter_conf.get("use_stemming", True),
                    )
                )
            elif filter_conf["type"] == "pruning":
                crawler_cfg.markdown_generator = DefaultMarkdownGenerator(
                    content_filter = PruningContentFilter(
                        user_query=filter_conf.get("query"),
                        threshold=filter_conf.get("threshold", 0.48)
                    )
                )
        
        # Handle json-extract option (takes precedence over extraction-config)
        if json_extract is not None:
            # Get LLM provider and token
            provider, token = setup_llm_config()
            
            # Default sophisticated instruction for structured data extraction
            default_instruction = """Analyze the web page content and extract structured data as JSON. 
If the page contains a list of items with repeated patterns, extract all items in an array. 
If the page is an article or contains unique content, extract a comprehensive JSON object with all relevant information.
Look at the content, intention of content, what it offers and find the data item(s) in the page.
Always return valid, properly formatted JSON."""
            
            
            default_instruction_with_user_query = """Analyze the web page content and extract structured data as JSON, following the below instruction and explanation of schema and always return valid, properly formatted JSON. \n\nInstruction:\n\n""" + json_extract
            
            # Determine instruction based on whether json_extract is empty or has content
            instruction = default_instruction_with_user_query if json_extract else default_instruction
            
            # Create LLM extraction strategy
            crawler_cfg.extraction_strategy = LLMExtractionStrategy(
                llm_config=LLMConfig(provider=provider, api_token=token),
                instruction=instruction,
                schema=load_schema_file(schema),  # Will be None if no schema is provided
                extraction_type="schema", #if schema else "block",
                apply_chunking=False,
                force_json_response=True,
                verbose=verbose,
            )
            
            # Set output to JSON if not explicitly specified
            if output == "all":
                output = "json"
                
        # Handle extraction strategy from config file (only if json-extract wasn't used)
        elif extraction_config:
            extract_conf = load_config_file(extraction_config)
            schema_data = load_schema_file(schema)
            
            # Check if type does not exist show proper message
            if not extract_conf.get("type"):
                raise click.ClickException("Extraction type not specified")
            if extract_conf["type"] not in ["llm", "json-css", "json-xpath"]:
                raise click.ClickException(f"Invalid extraction type: {extract_conf['type']}")
            
            if extract_conf["type"] == "llm":
                # if no provider show error emssage
                if not extract_conf.get("provider") or not extract_conf.get("api_token"):
                    raise click.ClickException("LLM provider and API token are required for LLM extraction")

                crawler_cfg.extraction_strategy = LLMExtractionStrategy(
                    llm_config=LLMConfig(provider=extract_conf["provider"], api_token=extract_conf["api_token"]),
                    instruction=extract_conf["instruction"],
                    schema=schema_data,
                    **extract_conf.get("params", {})
                )
            elif extract_conf["type"] == "json-css":
                crawler_cfg.extraction_strategy = JsonCssExtractionStrategy(
                    schema=schema_data
                )
            elif extract_conf["type"] == "json-xpath":
                crawler_cfg.extraction_strategy = JsonXPathExtractionStrategy(
                    schema=schema_data
                )
                

        # No cache
        if bypass_cache:
            crawler_cfg.cache_mode = CacheMode.BYPASS

        crawler_cfg.scraping_strategy = LXMLWebScrapingStrategy()    

        # Handle deep crawling configuration
        if deep_crawl:
            if deep_crawl == "bfs":
                crawler_cfg.deep_crawl_strategy = BFSDeepCrawlStrategy(
                    max_depth=3,
                    max_pages=max_pages
                )
            elif deep_crawl == "dfs":
                crawler_cfg.deep_crawl_strategy = DFSDeepCrawlStrategy(
                    max_depth=3,
                    max_pages=max_pages
                )
            elif deep_crawl == "best-first":
                crawler_cfg.deep_crawl_strategy = BestFirstCrawlingStrategy(
                    max_depth=3,
                    max_pages=max_pages
                )
            
            if verbose:
                console.print(f"[green]Deep crawling enabled:[/green] {deep_crawl} strategy, max {max_pages} pages")

        config = get_global_config()

        # Priority: CLI --verbose flag > global config > default (False)
        global_verbose = config.get("VERBOSE", False)
        effective_verbose = verbose if verbose else global_verbose

        browser_cfg.verbose = effective_verbose
        crawler_cfg.verbose = effective_verbose

        # Get JSON output config (priority: CLI flag > global config)
        if json_ensure_ascii is not None:
            ensure_ascii = json_ensure_ascii
        else:
            ensure_ascii = config.get("JSON_ENSURE_ASCII", USER_SETTINGS["JSON_ENSURE_ASCII"]["default"])

        # Run crawler
        result : CrawlResult = anyio.run(
            run_crawler,
            url,
            browser_cfg,
            crawler_cfg,
            verbose
        )

        # Handle deep crawl results (list) vs single result
        if isinstance(result, list):
            if len(result) == 0:
                click.echo("No results found during deep crawling")
                return
            # Use the first result for question answering and output
            main_result = result[0]
            all_results = result
        else:
            # Single result from regular crawling
            main_result = result
            all_results = [result]

        # Handle question
        if question:
            provider, token = setup_llm_config()
            markdown = main_result.markdown.raw_markdown
            anyio.run(stream_llm_response, url, markdown, question, provider, token)
            return
        
        # Handle output
        if not output_file:
            if output == "all":
                if isinstance(result, list):
                    output_data = [r.model_dump() for r in all_results]
                    click.echo(json.dumps(output_data, indent=2, ensure_ascii=ensure_ascii))
                else:
                    click.echo(json.dumps(main_result.model_dump(), indent=2, ensure_ascii=ensure_ascii))
            elif output == "json":
                print(main_result.extracted_content)
                extracted_items = json.loads(main_result.extracted_content)
                click.echo(json.dumps(extracted_items, indent=2, ensure_ascii=ensure_ascii))

            elif output in ["markdown", "md"]:
                if isinstance(result, list):
                    # Combine markdown from all crawled pages for deep crawl
                    for r in all_results:
                        click.echo(f"\n\n{'='*60}\n# {r.url}\n{'='*60}\n\n")
                        click.echo(r.markdown.raw_markdown)
                else:
                    click.echo(main_result.markdown.raw_markdown)
            elif output in ["markdown-fit", "md-fit"]:
                if isinstance(result, list):
                    # Combine fit markdown from all crawled pages for deep crawl
                    for r in all_results:
                        click.echo(f"\n\n{'='*60}\n# {r.url}\n{'='*60}\n\n")
                        click.echo(r.markdown.fit_markdown)
                else:
                    click.echo(main_result.markdown.fit_markdown)
        else:
            if output == "all":
                with open(output_file, "w", encoding="utf-8") as f:
                    if isinstance(result, list):
                        output_data = [r.model_dump() for r in all_results]
                        f.write(json.dumps(output_data, indent=2, ensure_ascii=ensure_ascii))
                    else:
                        f.write(json.dumps(main_result.model_dump(), indent=2, ensure_ascii=ensure_ascii))
            elif output == "json":
                with open(output_file, "w", encoding="utf-8") as f:
                    f.write(main_result.extracted_content)
            elif output in ["markdown", "md"]:
                with open(output_file, "w", encoding="utf-8") as f:
                    if isinstance(result, list):
                        # Combine markdown from all crawled pages for deep crawl
                        for r in all_results:
                            f.write(f"\n\n{'='*60}\n# {r.url}\n{'='*60}\n\n")
                            f.write(r.markdown.raw_markdown)
                    else:
                        f.write(main_result.markdown.raw_markdown)
            elif output in ["markdown-fit", "md-fit"]:
                with open(output_file, "w", encoding="utf-8") as f:
                    if isinstance(result, list):
                        # Combine fit markdown from all crawled pages for deep crawl
                        for r in all_results:
                            f.write(f"\n\n{'='*60}\n# {r.url}\n{'='*60}\n\n")
                            f.write(r.markdown.fit_markdown)
                    else:
                        f.write(main_result.markdown.fit_markdown)
            
    except Exception as e:
        raise click.ClickException(str(e))

@cli.command("examples")
def examples_cmd():
    """Show usage examples"""
    show_examples()

@cli.group("config")
def config_cmd():
    """Manage global configuration settings
    
    Commands to view and update global configuration settings:
    - list: Display all current configuration settings
    - get: Get the value of a specific setting
    - set: Set the value of a specific setting
    """
    pass

@config_cmd.command("list")
def config_list_cmd():
    """List all configuration settings"""
    config = get_global_config()
    
    table = Table(title="Crawl4AI Configuration", show_header=True, header_style="bold cyan", border_style="blue")
    table.add_column("Setting", style="cyan")
    table.add_column("Value", style="green")
    table.add_column("Default", style="yellow")
    table.add_column("Description", style="white")
    
    for key, setting in USER_SETTINGS.items():
        value = config.get(key, setting["default"])
        
        # Handle secret values
        display_value = value
        if setting.get("secret", False) and value:
            display_value = "********"
            
        # Handle boolean values
        if setting["type"] == "boolean":
            display_value = str(value).lower()
            default_value = str(setting["default"]).lower()
        else:
            default_value = str(setting["default"])
        
        table.add_row(
            key,
            str(display_value),
            default_value,
            setting["description"]
        )
    
    console.print(table)

@config_cmd.command("get")
@click.argument("key", required=True)
def config_get_cmd(key: str):
    """Get a specific configuration setting"""
    config = get_global_config()
    
    # Normalize key to uppercase
    key = key.upper()
    
    if key not in USER_SETTINGS:
        console.print(f"[red]Error: Unknown setting '{key}'[/red]")
        return
    
    value = config.get(key, USER_SETTINGS[key]["default"])
    
    # Handle secret values
    display_value = value
    if USER_SETTINGS[key].get("secret", False) and value:
        display_value = "********"
    
    console.print(f"[cyan]{key}[/cyan] = [green]{display_value}[/green]")
    console.print(f"[dim]Description: {USER_SETTINGS[key]['description']}[/dim]")

@config_cmd.command("set")
@click.argument("key", required=True)
@click.argument("value", required=True)
def config_set_cmd(key: str, value: str):
    """Set a configuration setting"""
    config = get_global_config()
    
    # Normalize key to uppercase
    key = key.upper()
    
    if key not in USER_SETTINGS:
        console.print(f"[red]Error: Unknown setting '{key}'[/red]")
        console.print(f"[yellow]Available settings: {', '.join(USER_SETTINGS.keys())}[/yellow]")
        return
    
    setting = USER_SETTINGS[key]
    
    # Type conversion and validation
    if setting["type"] == "boolean":
        if value.lower() in ["true", "yes", "1", "y"]:
            typed_value = True
        elif value.lower() in ["false", "no", "0", "n"]:
            typed_value = False
        else:
            console.print(f"[red]Error: Invalid boolean value. Use 'true' or 'false'.[/red]")
            return
    elif setting["type"] == "string":
        typed_value = value
        
        # Check if the value should be one of the allowed options
        if "options" in setting and value not in setting["options"]:
            console.print(f"[red]Error: Value must be one of: {', '.join(setting['options'])}[/red]")
            return
    
    # Update config
    config[key] = typed_value
    save_global_config(config)
    
    # Handle secret values for display
    display_value = typed_value
    if setting.get("secret", False) and typed_value:
        display_value = "********"
        
    console.print(f"[green]Successfully set[/green] [cyan]{key}[/cyan] = [green]{display_value}[/green]")

@cli.group("profiles", invoke_without_command=True)
@click.pass_context
def profiles_cmd(ctx):
    """Manage browser profiles for authenticated crawling

    Launch an interactive browser profile manager where you can:
    - List all existing profiles
    - Create new profiles for authenticated browsing
    - Delete unused profiles

    Subcommands:
      crwl profiles create <name>  - Create a new profile
      crwl profiles list           - List all profiles
      crwl profiles delete <name>  - Delete a profile

    Or run without subcommand for interactive menu:
      crwl profiles
    """
    # If no subcommand provided, run interactive manager
    if ctx.invoked_subcommand is None:
        anyio.run(manage_profiles)


@profiles_cmd.command("create")
@click.argument("name")
def profiles_create_cmd(name: str):
    """Create a new browser profile

    Opens a browser window for you to log in and set up your identity.
    Press 'q' in the terminal when finished to save the profile.

    Example:
      crwl profiles create github-auth
    """
    profiler = BrowserProfiler()
    console.print(Panel(f"[bold cyan]Creating Profile: {name}[/bold cyan]\n"
                      "A browser window will open for you to set up your identity.\n"
                      "Log in to sites, adjust settings, then press 'q' to save.",
                      border_style="cyan"))

    async def _create():
        try:
            profile_path = await profiler.create_profile(name)
            if profile_path:
                console.print(f"[green]Profile successfully created at:[/green] {profile_path}")
            else:
                console.print("[red]Failed to create profile.[/red]")
                sys.exit(1)
        except Exception as e:
            console.print(f"[red]Error creating profile: {str(e)}[/red]")
            sys.exit(1)

    anyio.run(_create)


@profiles_cmd.command("list")
def profiles_list_cmd():
    """List all browser profiles

    Example:
      crwl profiles list
    """
    profiler = BrowserProfiler()
    profiles = profiler.list_profiles()
    display_profiles_table(profiles)


@profiles_cmd.command("delete")
@click.argument("name")
@click.option("--force", "-f", is_flag=True, help="Skip confirmation")
def profiles_delete_cmd(name: str, force: bool):
    """Delete a browser profile

    Example:
      crwl profiles delete old-profile
      crwl profiles delete old-profile --force
    """
    profiler = BrowserProfiler()

    # Find profile by name
    profiles = profiler.list_profiles()
    profile = next((p for p in profiles if p["name"] == name), None)

    if not profile:
        console.print(f"[red]Profile not found:[/red] {name}")
        sys.exit(1)

    if not force:
        if not Confirm.ask(f"[yellow]Delete profile '{name}'?[/yellow]"):
            console.print("[cyan]Cancelled.[/cyan]")
            return

    try:
        profiler.delete_profile(name)
        console.print(f"[green]Profile '{name}' deleted successfully.[/green]")
    except Exception as e:
        console.print(f"[red]Error deleting profile: {str(e)}[/red]")
        sys.exit(1)


@cli.command("shrink")
@click.argument("profile_name")
@click.option(
    "--level", "-l",
    type=click.Choice(["light", "medium", "aggressive", "minimal"]),
    default="aggressive",
    help="Shrink level (default: aggressive)"
)
@click.option("--dry-run", "-n", is_flag=True, help="Preview without removing files")
def shrink_cmd(profile_name: str, level: str, dry_run: bool):
    """Shrink a browser profile to reduce storage.

    Removes cache, history, and other non-essential data while preserving
    authentication (cookies, localStorage, IndexedDB).

    Shrink levels:
      light      - Remove caches only
      medium     - Remove caches + history
      aggressive - Keep only auth data (recommended)
      minimal    - Keep only cookies + localStorage

    Examples:
      crwl shrink my_profile
      crwl shrink my_profile --level minimal
      crwl shrink my_profile --dry-run
    """
    profiler = BrowserProfiler()

    try:
        result = profiler.shrink(profile_name, ShrinkLevel(level), dry_run)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)

    # Display results
    action = "Would remove" if dry_run else "Removed"
    console.print(f"\n[cyan]Shrink Results ({level.upper()}):[/cyan]")
    console.print(f"  {action}: {len(result['removed'])} items")
    console.print(f"  Kept: {len(result['kept'])} items")
    console.print(f"  Space freed: {_format_size(result['bytes_freed'])}")

    if result.get("size_before"):
        console.print(f"  Size before: {_format_size(result['size_before'])}")
    if result.get("size_after"):
        console.print(f"  Size after: {_format_size(result['size_after'])}")

    if result["errors"]:
        console.print(f"\n[red]Errors ({len(result['errors'])}):[/red]")
        for err in result["errors"]:
            console.print(f"  - {err}")

    if dry_run:
        console.print("\n[yellow]Dry run - no files were actually removed.[/yellow]")

@cli.command(name="")
@click.argument("url", required=False)
@click.option("--example", is_flag=True, help="Show usage examples")
@click.option("--browser-config", "-B", type=click.Path(exists=True), help="Browser config file (YAML/JSON)")
@click.option("--crawler-config", "-C", type=click.Path(exists=True), help="Crawler config file (YAML/JSON)")
@click.option("--filter-config", "-f", type=click.Path(exists=True), help="Content filter config file")
@click.option("--extraction-config", "-e", type=click.Path(exists=True), help="Extraction strategy config file")
@click.option("--json-extract", "-j", is_flag=False, flag_value="", default=None, help="Extract structured data using LLM with optional description")
@click.option("--schema", "-s", type=click.Path(exists=True), help="JSON schema for extraction")
@click.option("--browser", "-b", type=str, callback=parse_key_values, help="Browser parameters as key1=value1,key2=value2")
@click.option("--crawler", "-c", type=str, callback=parse_key_values, help="Crawler parameters as key1=value1,key2=value2")
@click.option("--output", "-o", type=click.Choice(["all", "json", "markdown", "md", "markdown-fit", "md-fit"]), default="all")
@click.option("--bypass-cache", is_flag=True, default=True, help="Bypass cache when crawling")
@click.option("--question", "-q", help="Ask a question about the crawled content")
@click.option("--verbose", "-v", is_flag=True)
@click.option("--profile", "-p", help="Use a specific browser profile (by name)")
@click.option("--deep-crawl", type=click.Choice(["bfs", "dfs", "best-first"]), help="Enable deep crawling with specified strategy")
@click.option("--max-pages", type=int, default=10, help="Maximum number of pages to crawl in deep crawl mode")
@click.option("--json-ensure-ascii/--no-json-ensure-ascii", default=None, help="Escape non-ASCII characters in JSON output (default: from global config)")
def default(url: str, example: bool, browser_config: str, crawler_config: str, filter_config: str,
        extraction_config: str, json_extract: str, schema: str, browser: Dict, crawler: Dict,
        output: str, bypass_cache: bool, question: str, verbose: bool, profile: str, deep_crawl: str, max_pages: int, json_ensure_ascii: Optional[bool]):
    """Crawl4AI CLI - Web content extraction tool

    Simple Usage:
        crwl https://example.com
    
    Run with --example to see detailed usage examples.
    
    Other commands:
        crwl profiles   - Manage browser profiles for identity-based crawling
        crwl crawl      - Crawl a website with advanced options
        crwl cdp        - Launch browser with CDP debugging enabled
        crwl browser    - Manage builtin browser (start, stop, status, restart)
        crwl config     - Manage global configuration settings
        crwl examples   - Show more usage examples
        
    Configuration Examples:
        crwl config list                         - List all configuration settings
        crwl config get DEFAULT_LLM_PROVIDER     - Show current LLM provider
        crwl config set VERBOSE true             - Enable verbose mode globally
        crwl config set BROWSER_HEADLESS false   - Default to visible browser
    """

    if example:
        show_examples()
        return
        
    if not url:
        # Show help without error message
        ctx = click.get_current_context()
        click.echo(ctx.get_help())
        return
        
    # Forward to crawl command
    ctx = click.get_current_context()
    ctx.invoke(
        crawl_cmd, 
        url=url, 
        browser_config=browser_config,
        crawler_config=crawler_config,
        filter_config=filter_config,
        extraction_config=extraction_config,
        json_extract=json_extract,
        schema=schema,
        browser=browser,
        crawler=crawler,
        output=output,
        bypass_cache=bypass_cache,
        question=question,
        verbose=verbose,
        profile=profile,
        deep_crawl=deep_crawl,
        max_pages=max_pages,
        json_ensure_ascii=json_ensure_ascii
    )

def main():
    import sys
    if len(sys.argv) < 2 or sys.argv[1] not in cli.commands:
        sys.argv.insert(1, "crawl")
    cli()

if __name__ == "__main__":
    main()
```


## File: crawl4ai/extraction_strategy.py


```py
from abc import ABC, abstractmethod
import ast
import inspect
from typing import Any, List, Dict, Optional, Tuple, Pattern, Union
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import time
from enum import IntFlag, auto

from .prompts import PROMPT_EXTRACT_BLOCKS, PROMPT_EXTRACT_BLOCKS_WITH_INSTRUCTION, PROMPT_EXTRACT_SCHEMA_WITH_INSTRUCTION, JSON_SCHEMA_BUILDER_XPATH, PROMPT_EXTRACT_INFERRED_SCHEMA
from .config import (
    DEFAULT_PROVIDER,
    DEFAULT_PROVIDER_API_KEY,
    CHUNK_TOKEN_THRESHOLD,
    OVERLAP_RATE,
    WORD_TOKEN_RATE,
    HTML_EXAMPLE_DELIMITER,
)
from .utils import *  # noqa: F403

from .utils import (
    sanitize_html,
    escape_json_string,
    perform_completion_with_backoff,
    extract_xml_data,
    split_and_parse_json_objects,
    sanitize_input_encode,
    merge_chunks,
)
from .models import * # noqa: F403

from .models import TokenUsage

from .model_loader import * # noqa: F403
from .model_loader import (
    get_device,
    load_HF_embedding_model,
    load_text_multilabel_classifier,
    calculate_batch_size
)

from .types import LLMConfig, create_llm_config

from functools import partial
import numpy as np
import re
from bs4 import BeautifulSoup
from lxml import html, etree


def _strip_markdown_fences(text: str) -> str:
    """Strip markdown code fences (e.g. ```json ... ```) from LLM responses."""
    text = text.strip()
    return re.sub(
        r"^```(?:[a-zA-Z0-9_-]+)?\s*|```$", "", text, flags=re.MULTILINE
    ).strip()


def _get_top_level_structure(html_content: str, max_depth: int = 3) -> str:
    """Return a compact tag outline of the HTML body up to a given depth.

    Used in schema validation feedback when baseSelector matches 0 elements,
    so the LLM can see what top-level tags actually exist.
    """
    try:
        tree = html.fromstring(html_content)
    except Exception:
        return ""
    body = tree.xpath("//body")
    root = body[0] if body else tree
    lines = []

    def _walk(el, depth):
        if depth > max_depth or not isinstance(el.tag, str):
            return
        classes = el.get("class", "").split()
        cls_str = "." + ".".join(classes) if classes else ""
        id_str = f"#{el.get('id')}" if el.get("id") else ""
        lines.append("  " * depth + f"<{el.tag}{id_str}{cls_str}>")
        for child in el:
            _walk(child, depth + 1)

    _walk(root, 0)
    return "\n".join(lines[:60])


class ExtractionStrategy(ABC):
    """
    Abstract base class for all extraction strategies.
    """

    def __init__(self, input_format: str = "markdown", **kwargs):
        """
        Initialize the extraction strategy.

        Args:
            input_format: Content format to use for extraction.
                         Options: "markdown" (default), "html", "fit_markdown"
            **kwargs: Additional keyword arguments
        """
        self.input_format = input_format
        self.DEL = "<|DEL|>"
        self.name = self.__class__.__name__
        self.verbose = kwargs.get("verbose", False)

    @abstractmethod
    def extract(self, url: str, html: str, *q, **kwargs) -> List[Dict[str, Any]]:
        """
        Extract meaningful blocks or chunks from the given HTML.

        :param url: The URL of the webpage.
        :param html: The HTML content of the webpage.
        :return: A list of extracted blocks or chunks.
        """
        pass

    def run(self, url: str, sections: List[str], *q, **kwargs) -> List[Dict[str, Any]]:
        """
        Process sections of text in parallel by default.

        :param url: The URL of the webpage.
        :param sections: List of sections (strings) to process.
        :return: A list of processed JSON blocks.
        """
        extracted_content = []
        with ThreadPoolExecutor() as executor:
            futures = [
                executor.submit(self.extract, url, section, **kwargs)
                for section in sections
            ]
            for future in as_completed(futures):
                extracted_content.extend(future.result())
        return extracted_content

    async def arun(self, url: str, sections: List[str], *q, **kwargs) -> List[Dict[str, Any]]:
        """
        Async version: Process sections of text in parallel using asyncio.

        Default implementation runs the sync version in a thread pool.
        Subclasses can override this for true async processing.

        :param url: The URL of the webpage.
        :param sections: List of sections (strings) to process.
        :return: A list of processed JSON blocks.
        """
        import asyncio
        return await asyncio.to_thread(self.run, url, sections, *q, **kwargs)


class NoExtractionStrategy(ExtractionStrategy):
    """
    A strategy that does not extract any meaningful content from the HTML. It simply returns the entire HTML as a single block.
    """

    def extract(self, url: str, html: str, *q, **kwargs) -> List[Dict[str, Any]]:
        """
        Extract meaningful blocks or chunks from the given HTML.
        """
        return [{"index": 0, "content": html}]

    def run(self, url: str, sections: List[str], *q, **kwargs) -> List[Dict[str, Any]]:
        return [
            {"index": i, "tags": [], "content": section}
            for i, section in enumerate(sections)
        ]


#######################################################
# Strategies using clustering for text data extraction #
#######################################################


class CosineStrategy(ExtractionStrategy):
    """
    Extract meaningful blocks or chunks from the given HTML using cosine similarity.

    How it works:
    1. Pre-filter documents using embeddings and semantic_filter.
    2. Perform clustering using cosine similarity.
    3. Organize texts by their cluster labels, retaining order.
    4. Filter clusters by word count.
    5. Extract meaningful blocks or chunks from the filtered clusters.

    Attributes:
        semantic_filter (str): A keyword filter for document filtering.
        word_count_threshold (int): Minimum number of words per cluster.
        max_dist (float): The maximum cophenetic distance on the dendrogram to form clusters.
        linkage_method (str): The linkage method for hierarchical clustering.
        top_k (int): Number of top categories to extract.
        model_name (str): The name of the sentence-transformers model.
        sim_threshold (float): The similarity threshold for clustering.
    """

    def __init__(
        self,
        semantic_filter=None,
        word_count_threshold=10,
        max_dist=0.2,
        linkage_method="ward",
        top_k=3,
        model_name="sentence-transformers/all-MiniLM-L6-v2",
        sim_threshold=0.3,
        **kwargs,
    ):
        """
        Initialize the strategy with clustering parameters.

        Args:
            semantic_filter (str): A keyword filter for document filtering.
            word_count_threshold (int): Minimum number of words per cluster.
            max_dist (float): The maximum cophenetic distance on the dendrogram to form clusters.
            linkage_method (str): The linkage method for hierarchical clustering.
            top_k (int): Number of top categories to extract.
        """
        super().__init__(**kwargs)

        import numpy as np

        self.semantic_filter = semantic_filter
        self.word_count_threshold = word_count_threshold
        self.max_dist = max_dist
        self.linkage_method = linkage_method
        self.top_k = top_k
        self.sim_threshold = sim_threshold
        self.timer = time.time()
        self.verbose = kwargs.get("verbose", False)

        self.buffer_embeddings = np.array([])
        self.get_embedding_method = "direct"

        self.device = get_device()
        # import torch
        # self.device = torch.device('cpu')

        self.default_batch_size = calculate_batch_size(self.device)

        if self.verbose:
            print(f"[LOG] Loading Extraction Model for {self.device.type} device.")

        # if False and self.device.type == "cpu":
        #     self.model = load_onnx_all_MiniLM_l6_v2()
        #     self.tokenizer = self.model.tokenizer
        #     self.get_embedding_method = "direct"
        # else:

        self.tokenizer, self.model = load_HF_embedding_model(model_name)
        self.model.to(self.device)
        self.model.eval()

        self.get_embedding_method = "batch"

        self.buffer_embeddings = np.array([])

        # if model_name == "bert-base-uncased":
        #     self.tokenizer, self.model = load_bert_base_uncased()
        #     self.model.eval()  # Ensure the model is in evaluation mode
        #     self.get_embedding_method = "batch"
        # elif model_name == "BAAI/bge-small-en-v1.5":
        #     self.tokenizer, self.model = load_bge_small_en_v1_5()
        #     self.model.eval()  # Ensure the model is in evaluation mode
        #     self.get_embedding_method = "batch"
        # elif model_name == "sentence-transformers/all-MiniLM-L6-v2":
        #     self.model = load_onnx_all_MiniLM_l6_v2()
        #     self.tokenizer = self.model.tokenizer
        #     self.get_embedding_method = "direct"

        if self.verbose:
            print(f"[LOG] Loading Multilabel Classifier for {self.device.type} device.")

        self.nlp, _ = load_text_multilabel_classifier()
        # self.default_batch_size = 16 if self.device.type == 'cpu' else 64

        if self.verbose:
            print(
                f"[LOG] Model loaded {model_name}, models/reuters, took "
                + str(time.time() - self.timer)
                + " seconds"
            )

    def filter_documents_embeddings(
        self, documents: List[str], semantic_filter: str, at_least_k: int = 20
    ) -> List[str]:
        """
        Filter and sort documents based on the cosine similarity of their embeddings with the semantic_filter embedding.

        Args:
            documents (List[str]): A list of document texts.
            semantic_filter (str): A keyword filter for document filtering.
            at_least_k (int): The minimum number of documents to return.

        Returns:
            List[str]: A list of filtered and sorted document texts.
        """

        if not semantic_filter:
            return documents

        if len(documents) < at_least_k:
            at_least_k = max(1, len(documents) // 2)

        from sklearn.metrics.pairwise import cosine_similarity

        # Compute embedding for the keyword filter
        query_embedding = self.get_embeddings([semantic_filter])[0]

        # Compute embeddings for the documents
        document_embeddings = self.get_embeddings(documents)

        # Calculate cosine similarity between the query embedding and document embeddings
        similarities = cosine_similarity(
            [query_embedding], document_embeddings
        ).flatten()

        # Filter documents based on the similarity threshold
        filtered_docs = [
            (doc, sim)
            for doc, sim in zip(documents, similarities)
            if sim >= self.sim_threshold
        ]

        # If the number of filtered documents is less than at_least_k, sort remaining documents by similarity
        if len(filtered_docs) < at_least_k:
            remaining_docs = [
                (doc, sim)
                for doc, sim in zip(documents, similarities)
                if sim < self.sim_threshold
            ]
            remaining_docs.sort(key=lambda x: x[1], reverse=True)
            filtered_docs.extend(remaining_docs[: at_least_k - len(filtered_docs)])

        # Extract the document texts from the tuples
        filtered_docs = [doc for doc, _ in filtered_docs]

        return filtered_docs[:at_least_k]

    def get_embeddings(
        self, sentences: List[str], batch_size=None, bypass_buffer=False
    ):
        """
        Get BERT embeddings for a list of sentences.

        Args:
            sentences (List[str]): A list of text chunks (sentences).

        Returns:
            NumPy array of embeddings.
        """
        # if self.buffer_embeddings.any() and not bypass_buffer:
        #     return self.buffer_embeddings

        if self.device.type in ["cpu", "gpu", "cuda", "mps"]:
            import torch

            # Tokenize sentences and convert to tensor
            if batch_size is None:
                batch_size = self.default_batch_size

            all_embeddings = []
            for i in range(0, len(sentences), batch_size):
                batch_sentences = sentences[i : i + batch_size]
                encoded_input = self.tokenizer(
                    batch_sentences, padding=True, truncation=True, return_tensors="pt"
                )
                encoded_input = {
                    key: tensor.to(self.device) for key, tensor in encoded_input.items()
                }

                # Ensure no gradients are calculated
                with torch.no_grad():
                    model_output = self.model(**encoded_input)

                # Get embeddings from the last hidden state (mean pooling)
                embeddings = model_output.last_hidden_state.mean(dim=1).cpu().numpy()
                all_embeddings.append(embeddings)

            self.buffer_embeddings = np.vstack(all_embeddings)
        elif self.device.type == "cpu":
            # self.buffer_embeddings = self.model(sentences)
            if batch_size is None:
                batch_size = self.default_batch_size

            all_embeddings = []
            for i in range(0, len(sentences), batch_size):
                batch_sentences = sentences[i : i + batch_size]
                embeddings = self.model(batch_sentences)
                all_embeddings.append(embeddings)

            self.buffer_embeddings = np.vstack(all_embeddings)
        return self.buffer_embeddings

    def hierarchical_clustering(self, sentences: List[str], embeddings=None):
        """
        Perform hierarchical clustering on sentences and return cluster labels.

        Args:
            sentences (List[str]): A list of text chunks (sentences).

        Returns:
            NumPy array of cluster labels.
        """
        # Get embeddings
        from scipy.cluster.hierarchy import linkage, fcluster
        from scipy.spatial.distance import pdist

        self.timer = time.time()
        embeddings = self.get_embeddings(sentences, bypass_buffer=True)
        # print(f"[LOG] 🚀 Embeddings computed in {time.time() - self.timer:.2f} seconds")
        # Compute pairwise cosine distances
        distance_matrix = pdist(embeddings, "cosine")
        # Perform agglomerative clustering respecting order
        linked = linkage(distance_matrix, method=self.linkage_method)
        # Form flat clusters
        labels = fcluster(linked, self.max_dist, criterion="distance")
        return labels

    def filter_clusters_by_word_count(
        self, clusters: Dict[int, List[str]]
    ) -> Dict[int, List[str]]:
        """
        Filter clusters to remove those with a word count below the threshold.

        Args:
            clusters (Dict[int, List[str]]): Dictionary of clusters.

        Returns:
            Dict[int, List[str]]: Filtered dictionary of clusters.
        """
        filtered_clusters = {}
        for cluster_id, texts in clusters.items():
            # Concatenate texts for analysis
            full_text = " ".join(texts)
            # Count words
            word_count = len(full_text.split())

            # Keep clusters with word count above the threshold
            if word_count >= self.word_count_threshold:
                filtered_clusters[cluster_id] = texts

        return filtered_clusters

    def extract(self, url: str, html: str, *q, **kwargs) -> List[Dict[str, Any]]:
        """
        Extract clusters from HTML content using hierarchical clustering.

        Args:
            url (str): The URL of the webpage.
            html (str): The HTML content of the webpage.

        Returns:
            List[Dict[str, Any]]: A list of processed JSON blocks.
        """
        # Assume `html` is a list of text chunks for this strategy
        t = time.time()
        # Split by delimiter; fall back to double-newline splitting for raw text
        text_chunks = html.split(self.DEL)
        if len(text_chunks) == 1:
            text_chunks = [chunk.strip() for chunk in html.split("\n\n") if chunk.strip()]

        # Pre-filter documents using embeddings and semantic_filter
        text_chunks = self.filter_documents_embeddings(
            text_chunks, self.semantic_filter
        )

        if not text_chunks:
            return []

        # Perform clustering
        labels = self.hierarchical_clustering(text_chunks)
        # print(f"[LOG] 🚀 Clustering done in {time.time() - t:.2f} seconds")

        # Organize texts by their cluster labels, retaining order
        t = time.time()
        clusters = {}
        for index, label in enumerate(labels):
            clusters.setdefault(label, []).append(text_chunks[index])

        # Filter clusters by word count
        filtered_clusters = self.filter_clusters_by_word_count(clusters)

        # Convert filtered clusters to a sorted list of dictionaries
        cluster_list = [
            {"index": int(idx), "tags": [], "content": " ".join(filtered_clusters[idx])}
            for idx in sorted(filtered_clusters)
        ]

        if self.verbose:
            print(f"[LOG] 🚀 Assign tags using {self.device}")

        if self.device.type in ["gpu", "cuda", "mps", "cpu"]:
            labels = self.nlp([cluster["content"] for cluster in cluster_list])

            for cluster, label in zip(cluster_list, labels):
                cluster["tags"] = label
        # elif self.device.type == "cpu":
        #     # Process the text with the loaded model
        #     texts = [cluster['content'] for cluster in cluster_list]
        #     # Batch process texts
        #     docs = self.nlp.pipe(texts, disable=["tagger", "parser", "ner", "lemmatizer"])

        #     for doc, cluster in zip(docs, cluster_list):
        #         tok_k = self.top_k
        #         top_categories = sorted(doc.cats.items(), key=lambda x: x[1], reverse=True)[:tok_k]
        #         cluster['tags'] = [cat for cat, _ in top_categories]

        # for cluster in  cluster_list:
        #     doc = self.nlp(cluster['content'])
        #     tok_k = self.top_k
        #     top_categories = sorted(doc.cats.items(), key=lambda x: x[1], reverse=True)[:tok_k]
        #     cluster['tags'] = [cat for cat, _ in top_categories]

        if self.verbose:
            print(f"[LOG] 🚀 Categorization done in {time.time() - t:.2f} seconds")

        return cluster_list

    def run(self, url: str, sections: List[str], *q, **kwargs) -> List[Dict[str, Any]]:
        """
        Process sections using hierarchical clustering.

        Args:
            url (str): The URL of the webpage.
            sections (List[str]): List of sections (strings) to process.

        Returns:
        """
        # This strategy processes all sections together

        return self.extract(url, self.DEL.join(sections), **kwargs)


#######################################################
# Strategies using LLM-based extraction for text data #
#######################################################
class LLMExtractionStrategy(ExtractionStrategy):
    """
    A strategy that uses an LLM to extract meaningful content from the HTML.

    Attributes:
        llm_config: The LLM configuration object.
        instruction: The instruction to use for the LLM model.
        schema: Pydantic model schema for structured data.
        extraction_type: "block" or "schema".
        chunk_token_threshold: Maximum tokens per chunk.
        overlap_rate: Overlap between chunks.
        word_token_rate: Word to token conversion rate.
        apply_chunking: Whether to apply chunking.
        verbose: Whether to print verbose output.
        usages: List of individual token usages.
        total_usage: Accumulated token usage.
    """
    _UNWANTED_PROPS = {
            'provider' : 'Instead, use llm_config=LLMConfig(provider="...")',
            'api_token' : 'Instead, use llm_config=LlMConfig(api_token="...")',
            'base_url' : 'Instead, use llm_config=LLMConfig(base_url="...")',
            'api_base' : 'Instead, use llm_config=LLMConfig(base_url="...")',
        }
    def __init__(
        self,
        llm_config: 'LLMConfig' = None,
        instruction: str = None,
        schema: Dict = None,
        extraction_type="block",
        chunk_token_threshold=CHUNK_TOKEN_THRESHOLD,
        overlap_rate=OVERLAP_RATE,
        word_token_rate=WORD_TOKEN_RATE,
        apply_chunking=True,
        input_format: str = "markdown",
        force_json_response=False,
        verbose=False,
        # Deprecated arguments
        provider: str = DEFAULT_PROVIDER,
        api_token: Optional[str] = None,
        base_url: str = None,
        api_base: str = None,
        **kwargs,
    ):
        """
        Initialize the strategy with clustering parameters.

        Args:
            llm_config: The LLM configuration object.
            instruction: The instruction to use for the LLM model.
            schema: Pydantic model schema for structured data.
            extraction_type: "block" or "schema".
            chunk_token_threshold: Maximum tokens per chunk.
            overlap_rate: Overlap between chunks.
            word_token_rate: Word to token conversion rate.
            apply_chunking: Whether to apply chunking.
            input_format: Content format to use for extraction.
                            Options: "markdown" (default), "html", "fit_markdown"
            force_json_response: Whether to force a JSON response from the LLM.
            verbose: Whether to print verbose output.

            # Deprecated arguments, will be removed very soon
            provider: The provider to use for extraction. It follows the format <provider_name>/<model_name>, e.g., "ollama/llama3.3".
            api_token: The API token for the provider.
            base_url: The base URL for the API request.
            api_base: The base URL for the API request.
            extra_args: Additional arguments for the API request, such as temperature, max_tokens, etc.
        """
        super().__init__( input_format=input_format, **kwargs)
        self.llm_config = llm_config
        if not self.llm_config:
            self.llm_config = create_llm_config(
                provider=DEFAULT_PROVIDER,
                api_token=os.environ.get(DEFAULT_PROVIDER_API_KEY),
            )
        self.instruction = instruction
        self.extract_type = extraction_type
        self.schema = schema
        if schema:
            self.extract_type = "schema"
        self.force_json_response = force_json_response
        self.chunk_token_threshold = chunk_token_threshold or CHUNK_TOKEN_THRESHOLD
        self.overlap_rate = overlap_rate
        self.word_token_rate = word_token_rate
        self.apply_chunking = apply_chunking
        self.extra_args = kwargs.get("extra_args", {})
        if not self.apply_chunking:
            self.chunk_token_threshold = 1e9
        self.verbose = verbose
        self.usages = []  # Store individual usages
        self.total_usage = TokenUsage()  # Accumulated usage

        self.provider = provider
        self.api_token = api_token
        self.base_url = base_url
        self.api_base = api_base

    
    def __setattr__(self, name, value):
        """Handle attribute setting."""
        # TODO: Planning to set properties dynamically based on the __init__ signature
        sig = inspect.signature(self.__init__)
        all_params = sig.parameters  # Dictionary of parameter names and their details

        if name in self._UNWANTED_PROPS and value is not all_params[name].default:
            raise AttributeError(f"Setting '{name}' is deprecated. {self._UNWANTED_PROPS[name]}")
        
        super().__setattr__(name, value)  
        
    def extract(self, url: str, ix: int, html: str) -> List[Dict[str, Any]]:
        """
        Extract meaningful blocks or chunks from the given HTML using an LLM.

        How it works:
        1. Construct a prompt with variables.
        2. Make a request to the LLM using the prompt.
        3. Parse the response and extract blocks or chunks.

        Args:
            url: The URL of the webpage.
            ix: Index of the block.
            html: The HTML content of the webpage.

        Returns:
            A list of extracted blocks or chunks.
        """
        if self.verbose:
            # print("[LOG] Extracting blocks from URL:", url)
            print(f"[LOG] Call LLM for {url} - block index: {ix}")

        variable_values = {
            "URL": url,
            "HTML": escape_json_string(sanitize_html(html)),
        }

        prompt_with_variables = PROMPT_EXTRACT_BLOCKS
        if self.instruction:
            variable_values["REQUEST"] = self.instruction
            prompt_with_variables = PROMPT_EXTRACT_BLOCKS_WITH_INSTRUCTION

        if self.extract_type == "schema" and self.schema:
            variable_values["SCHEMA"] = json.dumps(self.schema, indent=2) # if type of self.schema is dict else self.schema
            prompt_with_variables = PROMPT_EXTRACT_SCHEMA_WITH_INSTRUCTION

        if self.extract_type == "schema" and not self.schema:
            prompt_with_variables = PROMPT_EXTRACT_INFERRED_SCHEMA

        for variable in variable_values:
            prompt_with_variables = prompt_with_variables.replace(
                "{" + variable + "}", variable_values[variable]
            )

        try:
            response = perform_completion_with_backoff(
                self.llm_config.provider,
                prompt_with_variables,
                self.llm_config.api_token,
                base_url=self.llm_config.base_url,
                json_response=self.force_json_response,
                extra_args=self.extra_args,
                base_delay=self.llm_config.backoff_base_delay,
                max_attempts=self.llm_config.backoff_max_attempts,
                exponential_factor=self.llm_config.backoff_exponential_factor
            )  # , json_response=self.extract_type == "schema")
            # Track usage
            usage = TokenUsage(
                completion_tokens=response.usage.completion_tokens,
                prompt_tokens=response.usage.prompt_tokens,
                total_tokens=response.usage.total_tokens,
                completion_tokens_details=response.usage.completion_tokens_details.__dict__
                if response.usage.completion_tokens_details
                else {},
                prompt_tokens_details=response.usage.prompt_tokens_details.__dict__
                if response.usage.prompt_tokens_details
                else {},
            )
            self.usages.append(usage)

            # Update totals
            self.total_usage.completion_tokens += usage.completion_tokens
            self.total_usage.prompt_tokens += usage.prompt_tokens
            self.total_usage.total_tokens += usage.total_tokens

            try:
                content = response.choices[0].message.content
                blocks = None

                if not content:
                    finish_reason = getattr(response.choices[0], "finish_reason", "unknown")
                    blocks = [{"index": 0, "error": True, "tags": ["error"],
                               "content": f"LLM returned no content (finish_reason: {finish_reason})"}]
                elif self.force_json_response:
                    blocks = json.loads(_strip_markdown_fences(content))
                    if isinstance(blocks, dict):
                        # If it has only one key which calue is list then assign that to blocks, exampled: {"news": [..]}
                        if len(blocks) == 1 and isinstance(list(blocks.values())[0], list):
                            blocks = list(blocks.values())[0]
                        else:
                            # If it has only one key which value is not list then assign that to blocks, exampled: { "article_id": "1234", ... }
                            blocks = [blocks]
                    elif isinstance(blocks, list):
                        # If it is a list then assign that to blocks
                        blocks = blocks
                else: 
                    # blocks = extract_xml_data(["blocks"], response.choices[0].message.content)["blocks"]
                    blocks = extract_xml_data(["blocks"], content)["blocks"]
                    blocks = json.loads(blocks)

                for block in blocks:
                    block["error"] = False
            except Exception:
                raw_content = response.choices[0].message.content or ""
                parsed, unparsed = split_and_parse_json_objects(raw_content)
                blocks = parsed
                if unparsed:
                    blocks.append(
                        {"index": 0, "error": True, "tags": ["error"], "content": unparsed}
                    )

            if self.verbose:
                print(
                    "[LOG] Extracted",
                    len(blocks),
                    "blocks from URL:",
                    url,
                    "block index:",
                    ix,
                )
            return blocks
        except Exception as e:
            if self.verbose:
                print(f"[LOG] Error in LLM extraction: {e}")
            # Add error information to extracted_content
            return [
                {
                    "index": ix,
                    "error": True,
                    "tags": ["error"],
                    "content": str(e),
                }
            ]

    def _merge(self, documents, chunk_token_threshold, overlap) -> List[str]:
        """
        Merge documents into sections based on chunk_token_threshold and overlap.
        """
        sections =  merge_chunks(
            docs = documents,
            target_size= chunk_token_threshold,
            overlap=overlap,
            word_token_ratio=self.word_token_rate
        )
        return sections

    def run(self, url: str, sections: List[str]) -> List[Dict[str, Any]]:
        """
        Process sections sequentially with a delay for rate limiting issues, specifically for LLMExtractionStrategy.

        Args:
            url: The URL of the webpage.
            sections: List of sections (strings) to process.

        Returns:
            A list of extracted blocks or chunks.
        """

        merged_sections = self._merge(
            sections,
            self.chunk_token_threshold,
            overlap=int(self.chunk_token_threshold * self.overlap_rate),
        )
        extracted_content = []
        if self.llm_config.provider.startswith("groq/"):
            # Sequential processing with a delay
            for ix, section in enumerate(merged_sections):
                extract_func = partial(self.extract, url)
                extracted_content.extend(
                    extract_func(ix, sanitize_input_encode(section))
                )
                time.sleep(0.5)  # 500 ms delay between each processing
        else:
            # Parallel processing using ThreadPoolExecutor
            # extract_func = partial(self.extract, url)
            # for ix, section in enumerate(merged_sections):
            #     extracted_content.append(extract_func(ix, section))

            with ThreadPoolExecutor(max_workers=4) as executor:
                extract_func = partial(self.extract, url)
                futures = [
                    executor.submit(extract_func, ix, sanitize_input_encode(section))
                    for ix, section in enumerate(merged_sections)
                ]

                for future in as_completed(futures):
                    try:
                        extracted_content.extend(future.result())
                    except Exception as e:
                        if self.verbose:
                            print(f"Error in thread execution: {e}")
                        # Add error information to extracted_content
                        extracted_content.append(
                            {
                                "index": 0,
                                "error": True,
                                "tags": ["error"],
                                "content": str(e),
                            }
                        )

        return extracted_content

    async def aextract(self, url: str, ix: int, html: str) -> List[Dict[str, Any]]:
        """
        Async version: Extract meaningful blocks or chunks from the given HTML using an LLM.

        How it works:
        1. Construct a prompt with variables.
        2. Make an async request to the LLM using the prompt.
        3. Parse the response and extract blocks or chunks.

        Args:
            url: The URL of the webpage.
            ix: Index of the block.
            html: The HTML content of the webpage.

        Returns:
            A list of extracted blocks or chunks.
        """
        from .utils import aperform_completion_with_backoff

        if self.verbose:
            print(f"[LOG] Call LLM for {url} - block index: {ix}")

        variable_values = {
            "URL": url,
            "HTML": escape_json_string(sanitize_html(html)),
        }

        prompt_with_variables = PROMPT_EXTRACT_BLOCKS
        if self.instruction:
            variable_values["REQUEST"] = self.instruction
            prompt_with_variables = PROMPT_EXTRACT_BLOCKS_WITH_INSTRUCTION

        if self.extract_type == "schema" and self.schema:
            variable_values["SCHEMA"] = json.dumps(self.schema, indent=2)
            prompt_with_variables = PROMPT_EXTRACT_SCHEMA_WITH_INSTRUCTION

        if self.extract_type == "schema" and not self.schema:
            prompt_with_variables = PROMPT_EXTRACT_INFERRED_SCHEMA

        for variable in variable_values:
            prompt_with_variables = prompt_with_variables.replace(
                "{" + variable + "}", variable_values[variable]
            )

        try:
            response = await aperform_completion_with_backoff(
                self.llm_config.provider,
                prompt_with_variables,
                self.llm_config.api_token,
                base_url=self.llm_config.base_url,
                json_response=self.force_json_response,
                extra_args=self.extra_args,
                base_delay=self.llm_config.backoff_base_delay,
                max_attempts=self.llm_config.backoff_max_attempts,
                exponential_factor=self.llm_config.backoff_exponential_factor
            )
            # Track usage
            usage = TokenUsage(
                completion_tokens=response.usage.completion_tokens,
                prompt_tokens=response.usage.prompt_tokens,
                total_tokens=response.usage.total_tokens,
                completion_tokens_details=response.usage.completion_tokens_details.__dict__
                if response.usage.completion_tokens_details
                else {},
                prompt_tokens_details=response.usage.prompt_tokens_details.__dict__
                if response.usage.prompt_tokens_details
                else {},
            )
            self.usages.append(usage)

            # Update totals
            self.total_usage.completion_tokens += usage.completion_tokens
            self.total_usage.prompt_tokens += usage.prompt_tokens
            self.total_usage.total_tokens += usage.total_tokens

            try:
                content = response.choices[0].message.content
                blocks = None

                if not content:
                    finish_reason = getattr(response.choices[0], "finish_reason", "unknown")
                    blocks = [{"index": 0, "error": True, "tags": ["error"],
                               "content": f"LLM returned no content (finish_reason: {finish_reason})"}]
                elif self.force_json_response:
                    blocks = json.loads(_strip_markdown_fences(content))
                    if isinstance(blocks, dict):
                        if len(blocks) == 1 and isinstance(list(blocks.values())[0], list):
                            blocks = list(blocks.values())[0]
                        else:
                            blocks = [blocks]
                    elif isinstance(blocks, list):
                        blocks = blocks
                else:
                    blocks = extract_xml_data(["blocks"], content)["blocks"]
                    blocks = json.loads(blocks)

                for block in blocks:
                    block["error"] = False
            except Exception:
                raw_content = response.choices[0].message.content or ""
                parsed, unparsed = split_and_parse_json_objects(raw_content)
                blocks = parsed
                if unparsed:
                    blocks.append(
                        {"index": 0, "error": True, "tags": ["error"], "content": unparsed}
                    )

            if self.verbose:
                print(
                    "[LOG] Extracted",
                    len(blocks),
                    "blocks from URL:",
                    url,
                    "block index:",
                    ix,
                )
            return blocks
        except Exception as e:
            if self.verbose:
                print(f"[LOG] Error in LLM extraction: {e}")
            return [
                {
                    "index": ix,
                    "error": True,
                    "tags": ["error"],
                    "content": str(e),
                }
            ]

    async def arun(self, url: str, sections: List[str]) -> List[Dict[str, Any]]:
        """
        Async version: Process sections with true parallelism using asyncio.gather.

        Args:
            url: The URL of the webpage.
            sections: List of sections (strings) to process.

        Returns:
            A list of extracted blocks or chunks.
        """
        import asyncio

        merged_sections = self._merge(
            sections,
            self.chunk_token_threshold,
            overlap=int(self.chunk_token_threshold * self.overlap_rate),
        )

        extracted_content = []

        # Create tasks for all sections to run in parallel
        tasks = [
            self.aextract(url, ix, sanitize_input_encode(section))
            for ix, section in enumerate(merged_sections)
        ]

        # Execute all tasks concurrently
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Process results
        for result in results:
            if isinstance(result, Exception):
                if self.verbose:
                    print(f"Error in async extraction: {result}")
                extracted_content.append(
                    {
                        "index": 0,
                        "error": True,
                        "tags": ["error"],
                        "content": str(result),
                    }
                )
            else:
                extracted_content.extend(result)

        return extracted_content

    def show_usage(self) -> None:
        """Print a detailed token usage report showing total and per-request usage."""
        print("\n=== Token Usage Summary ===")
        print(f"{'Type':<15} {'Count':>12}")
        print("-" * 30)
        print(f"{'Completion':<15} {self.total_usage.completion_tokens:>12,}")
        print(f"{'Prompt':<15} {self.total_usage.prompt_tokens:>12,}")
        print(f"{'Total':<15} {self.total_usage.total_tokens:>12,}")

        print("\n=== Usage History ===")
        print(f"{'Request #':<10} {'Completion':>12} {'Prompt':>12} {'Total':>12}")
        print("-" * 48)
        for i, usage in enumerate(self.usages, 1):
            print(
                f"{i:<10} {usage.completion_tokens:>12,} {usage.prompt_tokens:>12,} {usage.total_tokens:>12,}"
            )


#######################################################
# New extraction strategies for JSON-based extraction #
#######################################################

# Safe builtins allowed in computed field expressions
_SAFE_EVAL_BUILTINS = {
    "str": str, "int": int, "float": float, "bool": bool,
    "len": len, "round": round, "abs": abs, "min": min, "max": max,
    "sum": sum, "sorted": sorted, "reversed": reversed,
    "list": list, "dict": dict, "tuple": tuple, "set": set,
    "enumerate": enumerate, "zip": zip, "map": map, "filter": filter,
    "any": any, "all": all, "range": range,
    "True": True, "False": False, "None": None,
    "isinstance": isinstance, "type": type,
}


def _safe_eval_expression(expression: str, local_vars: dict) -> Any:
    """
    Evaluate a computed field expression safely using AST validation.

    Allows simple transforms (math, string methods, attribute access on data)
    while blocking dangerous operations (__import__, dunder access, etc.).

    Args:
        expression: The Python expression string to evaluate.
        local_vars: The local variables (extracted item fields) available to the expression.

    Returns:
        The result of evaluating the expression.

    Raises:
        ValueError: If the expression contains disallowed constructs.
    """
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as e:
        raise ValueError(f"Invalid expression syntax: {e}")

    for node in ast.walk(tree):
        # Block import statements
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            raise ValueError("Import statements are not allowed in expressions")

        # Block attribute access to dunder attributes (e.g., __class__, __globals__)
        if isinstance(node, ast.Attribute) and node.attr.startswith("_"):
            raise ValueError(
                f"Access to private/dunder attribute '{node.attr}' is not allowed"
            )

        # Block calls to __import__ or any name starting with _
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id.startswith("_"):
                raise ValueError(
                    f"Calling '{func.id}' is not allowed in expressions"
                )
            if isinstance(func, ast.Attribute) and func.attr.startswith("_"):
                raise ValueError(
                    f"Calling '{func.attr}' is not allowed in expressions"
                )

    safe_globals = {"__builtins__": _SAFE_EVAL_BUILTINS}
    return eval(compile(tree, "<expression>", "eval"), safe_globals, local_vars)


class JsonElementExtractionStrategy(ExtractionStrategy):
    """
    Abstract base class for extracting structured JSON from HTML content.

    How it works:
    1. Parses HTML content using the `_parse_html` method.
    2. Uses a schema to define base selectors, fields, and transformations.
    3. Extracts data hierarchically, supporting nested fields and lists.
    4. Handles computed fields with expressions or functions.

    Attributes:
        DEL (str): Delimiter used to combine HTML sections. Defaults to '\n'.
        schema (Dict[str, Any]): The schema defining the extraction rules.
        verbose (bool): Enables verbose logging for debugging purposes.

    Methods:
        extract(url, html_content, *q, **kwargs): Extracts structured data from HTML content.
        _extract_item(element, fields): Extracts fields from a single element.
        _extract_single_field(element, field): Extracts a single field based on its type.
        _apply_transform(value, transform): Applies a transformation to a value.
        _compute_field(item, field): Computes a field value using an expression or function.
        run(url, sections, *q, **kwargs): Combines HTML sections and runs the extraction strategy.

    Abstract Methods:
        _parse_html(html_content): Parses raw HTML into a structured format (e.g., BeautifulSoup or lxml).
        _get_base_elements(parsed_html, selector): Retrieves base elements using a selector.
        _get_elements(element, selector): Retrieves child elements using a selector.
        _get_element_text(element): Extracts text content from an element.
        _get_element_html(element): Extracts raw HTML from an element.
        _get_element_attribute(element, attribute): Extracts an attribute's value from an element.
    """

    DEL = "\n"

    def __init__(self, schema: Dict[str, Any], **kwargs):
        """
        Initialize the JSON element extraction strategy with a schema.

        Args:
            schema (Dict[str, Any]): The schema defining the extraction rules.
        """
        super().__init__(**kwargs)
        self.schema = schema
        self.verbose = kwargs.get("verbose", False)

    def extract(
        self, url: str, html_content: str, *q, **kwargs
    ) -> List[Dict[str, Any]]:
        """
        Extract structured data from HTML content.

        How it works:
        1. Parses the HTML content using the `_parse_html` method.
        2. Identifies base elements using the schema's base selector.
        3. Extracts fields from each base element using `_extract_item`.

        Args:
            url (str): The URL of the page being processed.
            html_content (str): The raw HTML content to parse and extract.
            *q: Additional positional arguments.
            **kwargs: Additional keyword arguments for custom extraction.

        Returns:
            List[Dict[str, Any]]: A list of extracted items, each represented as a dictionary.
        """

        parsed_html = self._parse_html(html_content)
        base_elements = self._get_base_elements(
            parsed_html, self.schema["baseSelector"]
        )

        results = []
        for element in base_elements:
            # Extract base element attributes
            item = {}
            if "baseFields" in self.schema:
                for field in self.schema["baseFields"]:
                    value = self._extract_single_field(element, field)
                    if value is not None:
                        item[field["name"]] = value

            # Extract child fields
            field_data = self._extract_item(element, self.schema["fields"])
            item.update(field_data)

            if item:
                results.append(item)

        return results

    @abstractmethod
    def _parse_html(self, html_content: str):
        """Parse HTML content into appropriate format"""
        pass

    @abstractmethod
    def _get_base_elements(self, parsed_html, selector: str):
        """Get all base elements using the selector"""
        pass

    @abstractmethod
    def _get_elements(self, element, selector: str):
        """Get child elements using the selector"""
        pass

    def _extract_field(self, element, field):
        try:
            if "source" in field:
                element = self._resolve_source(element, field["source"])
                if element is None:
                    return field.get("default")

            if field["type"] == "nested":
                nested_elements = self._get_elements(element, field["selector"])
                nested_element = nested_elements[0] if nested_elements else None
                return (
                    self._extract_item(nested_element, field["fields"])
                    if nested_element
                    else {}
                )

            if field["type"] == "list":
                elements = self._get_elements(element, field["selector"])
                return [self._extract_list_item(el, field["fields"]) for el in elements]

            if field["type"] == "nested_list":
                elements = self._get_elements(element, field["selector"])
                return [self._extract_item(el, field["fields"]) for el in elements]

            return self._extract_single_field(element, field)
        except Exception as e:
            if self.verbose:
                print(f"Error extracting field {field['name']}: {str(e)}")
            return field.get("default")

    def _extract_single_field(self, element, field):
        """
        Extract a single field based on its type.

        How it works:
        1. Selects the target element using the field's selector.
        2. Extracts the field value based on its type (e.g., text, attribute, regex).
        3. Applies transformations if defined in the schema.

        Args:
            element: The base element to extract the field from.
            field (Dict[str, Any]): The field definition in the schema.

        Returns:
            Any: The extracted field value.
        """

        if "selector" in field:
            selected = self._get_elements(element, field["selector"])
            if not selected:
                return field.get("default")
            selected = selected[0]
        else:
            selected = element

        type_pipeline = field["type"]
        if not isinstance(type_pipeline, list):
            type_pipeline = [type_pipeline]
        value = selected
        for step in type_pipeline:
            if step == "text":
                value = self._get_element_text(value)
            elif step == "attribute":
                value = self._get_element_attribute(value, field["attribute"])
            elif step == "html":
                value = self._get_element_html(value)
            elif step == "regex":
                pattern = field.get("pattern")
                if pattern:
                    # If value is still an element, extract text first (backward compat)
                    if not isinstance(value, str):
                        value = self._get_element_text(value)
                    if isinstance(value, str):
                        match = re.search(pattern, value)
                        value = match.group(field.get("group", 1)) if match else None
                    else:
                        value = None
            if value is None:
                break

        if "transform" in field:
            value = self._apply_transform(value, field["transform"])

        return value if value is not None else field.get("default")

    def _extract_list_item(self, element, fields):
        item = {}
        for field in fields:
            value = self._extract_single_field(element, field)
            if value is not None:
                item[field["name"]] = value
        return item

    def _extract_item(self, element, fields):
        """
        Extracts fields from a given element.

        How it works:
        1. Iterates through the fields defined in the schema.
        2. Handles computed, single, and nested field types.
        3. Updates the item dictionary with extracted field values.

        Args:
            element: The base element to extract fields from.
            fields (List[Dict[str, Any]]): The list of fields to extract.

        Returns:
            Dict[str, Any]: A dictionary representing the extracted item.
        """

        item = {}
        for field in fields:
            if field["type"] == "computed":
                value = self._compute_field(item, field)
            else:
                value = self._extract_field(element, field)
            if value is not None:
                item[field["name"]] = value
        return item

    def _apply_transform(self, value, transform):
        """
        Apply a transformation to a value.

        How it works:
        1. Checks the transformation type (e.g., `lowercase`, `strip`).
        2. Applies the transformation to the value.
        3. Returns the transformed value.

        Args:
            value (str): The value to transform.
            transform (str): The type of transformation to apply.

        Returns:
            str: The transformed value.
        """

        if transform == "lowercase":
            return value.lower()
        elif transform == "uppercase":
            return value.upper()
        elif transform == "strip":
            return value.strip()
        return value

    def _compute_field(self, item, field):
        try:
            if "expression" in field:
                return _safe_eval_expression(field["expression"], item)
            elif "function" in field:
                return field["function"](item)
        except Exception as e:
            if self.verbose:
                print(f"Error computing field {field['name']}: {str(e)}")
            return field.get("default")

    def run(self, url: str, sections: List[str], *q, **kwargs) -> List[Dict[str, Any]]:
        """
        Run the extraction strategy on a combined HTML content.

        How it works:
        1. Combines multiple HTML sections using the `DEL` delimiter.
        2. Calls the `extract` method with the combined HTML.

        Args:
            url (str): The URL of the page being processed.
            sections (List[str]): A list of HTML sections.
            *q: Additional positional arguments.
            **kwargs: Additional keyword arguments for custom extraction.

        Returns:
            List[Dict[str, Any]]: A list of extracted items.
        """

        combined_html = self.DEL.join(sections)
        return self.extract(url, combined_html, **kwargs)

    @abstractmethod
    def _get_element_text(self, element) -> str:
        """Get text content from element"""
        pass

    @abstractmethod
    def _get_element_html(self, element) -> str:
        """Get HTML content from element"""
        pass

    @abstractmethod
    def _get_element_attribute(self, element, attribute: str):
        """Get attribute value from element"""
        pass

    @abstractmethod
    def _resolve_source(self, element, source: str):
        """Navigate to a sibling element relative to the base element.

        Used when a field's data lives in a sibling of the base element
        rather than a descendant. For example, Hacker News splits each
        submission across two sibling <tr> rows.

        Args:
            element: The current base element.
            source: A sibling selector string. Currently supports the
                ``"+ <selector>"`` syntax which navigates to the next
                sibling matching ``<selector>``.

        Returns:
            The resolved sibling element, or ``None`` if not found.
        """
        pass

    @staticmethod
    def _validate_schema(
        schema: dict,
        html_content: str,
        schema_type: str = "CSS",
        expected_fields: Optional[List[str]] = None,
    ) -> dict:
        """Run the generated schema against HTML and return a diagnostic result.

        Args:
            schema: The extraction schema to validate.
            html_content: The HTML to validate against.
            schema_type: "CSS" or "XPATH".
            expected_fields: When provided, enables strict mode — success
                requires ALL expected fields to be present and populated.
                When None, uses fuzzy mode (populated_fields > 0).

        Returns a dict with keys: success, base_elements_found, total_fields,
        populated_fields, field_coverage, field_details, issues,
        sample_base_html, top_level_structure.
        """
        result = {
            "success": False,
            "base_elements_found": 0,
            "total_fields": 0,
            "populated_fields": 0,
            "field_coverage": 0.0,
            "field_details": [],
            "issues": [],
            "sample_base_html": "",
            "top_level_structure": "",
        }

        try:
            StrategyClass = (
                JsonCssExtractionStrategy
                if schema_type.upper() == "CSS"
                else JsonXPathExtractionStrategy
            )
            strategy = StrategyClass(schema=schema)
            items = strategy.extract(url="", html_content=html_content)
        except Exception as e:
            result["issues"].append(f"Extraction crashed: {e}")
            return result

        # Count base elements directly
        try:
            parsed = strategy._parse_html(html_content)
            base_elements = strategy._get_base_elements(parsed, schema["baseSelector"])
            result["base_elements_found"] = len(base_elements)

            # Grab sample innerHTML of first base element (truncated)
            if base_elements:
                sample = strategy._get_element_html(base_elements[0])
                result["sample_base_html"] = sample[:2000]
        except Exception:
            pass

        if result["base_elements_found"] == 0:
            result["issues"].append(
                f"baseSelector '{schema.get('baseSelector', '')}' matched 0 elements"
            )
            result["top_level_structure"] = _get_top_level_structure(html_content)
            return result

        # Analyze field coverage
        all_fields = schema.get("fields", [])
        field_names = [f["name"] for f in all_fields]
        result["total_fields"] = len(field_names)

        for fname in field_names:
            values = [item.get(fname) for item in items]
            populated_count = sum(1 for v in values if v is not None and v != "")
            sample_val = next((v for v in values if v is not None and v != ""), None)
            if sample_val is not None:
                sample_val = str(sample_val)[:120]
            result["field_details"].append({
                "name": fname,
                "populated_count": populated_count,
                "total_count": len(items),
                "sample_value": sample_val,
            })

        result["populated_fields"] = sum(
            1 for fd in result["field_details"] if fd["populated_count"] > 0
        )
        if result["total_fields"] > 0:
            result["field_coverage"] = result["populated_fields"] / result["total_fields"]

        # Build issues
        if result["populated_fields"] == 0:
            result["issues"].append(
                "All fields returned None/empty — selectors likely wrong"
            )
        else:
            empty_fields = [
                fd["name"]
                for fd in result["field_details"]
                if fd["populated_count"] == 0
            ]
            if empty_fields:
                result["issues"].append(
                    f"Fields always empty: {', '.join(empty_fields)}"
                )

        # Check for missing expected fields (strict mode)
        if expected_fields:
            schema_field_names = {f["name"] for f in schema.get("fields", [])}
            missing = [f for f in expected_fields if f not in schema_field_names]
            if missing:
                result["issues"].append(
                    f"Expected fields missing from schema: {', '.join(missing)}"
                )

        # Success criteria
        if expected_fields:
            # Strict: all expected fields must exist in schema AND be populated
            schema_field_names = {f["name"] for f in schema.get("fields", [])}
            populated_names = {
                fd["name"] for fd in result["field_details"] if fd["populated_count"] > 0
            }
            result["success"] = (
                result["base_elements_found"] > 0
                and all(f in populated_names for f in expected_fields)
            )
        else:
            # Fuzzy: at least something extracted
            result["success"] = (
                result["base_elements_found"] > 0 and result["populated_fields"] > 0
            )
        return result

    @staticmethod
    def _build_feedback_message(
        validation_result: dict,
        schema: dict,
        attempt: int,
        is_repeated: bool,
    ) -> str:
        """Build a structured feedback message from a validation result."""
        vr = validation_result
        parts = []

        parts.append(f"## Schema Validation — Attempt {attempt}")

        # Base selector
        if vr["base_elements_found"] == 0:
            parts.append(
                f"**CRITICAL:** baseSelector `{schema.get('baseSelector', '')}` "
                f"matched **0 elements**. The schema cannot extract anything."
            )
            if vr["top_level_structure"]:
                parts.append(
                    "Here is the top-level HTML structure so you can pick a valid selector:\n```\n"
                    + vr["top_level_structure"]
                    + "\n```"
                )
        else:
            parts.append(
                f"baseSelector matched **{vr['base_elements_found']}** element(s)."
            )

        # Field coverage table
        if vr["field_details"]:
            parts.append(
                f"\n**Field coverage:** {vr['populated_fields']}/{vr['total_fields']} fields have data\n"
            )
            parts.append("| Field | Populated | Sample |")
            parts.append("|-------|-----------|--------|")
            for fd in vr["field_details"]:
                sample = fd["sample_value"] or "*(empty)*"
                parts.append(
                    f"| {fd['name']} | {fd['populated_count']}/{fd['total_count']} | {sample} |"
                )

        # Issues
        if vr["issues"]:
            parts.append("\n**Issues:**")
            for issue in vr["issues"]:
                parts.append(f"- {issue}")

        # Sample base HTML when all fields empty
        if vr["populated_fields"] == 0 and vr["sample_base_html"]:
            parts.append(
                "\nHere is the innerHTML of the first base element — "
                "use it to find correct child selectors:\n```html\n"
                + vr["sample_base_html"]
                + "\n```"
            )

        # Repeated schema warning
        if is_repeated:
            parts.append(
                "\n**WARNING:** You returned the exact same schema as before. "
                "You MUST change the selectors to fix the issues above."
            )

        parts.append(
            "\nPlease fix the schema and return ONLY valid JSON, nothing else."
        )
        return "\n".join(parts)

    @staticmethod
    async def _infer_target_json(query: str, html_snippet: str, llm_config, url: str = None, usage: 'TokenUsage' = None) -> Optional[dict]:
        """Infer a target JSON example from a query and HTML snippet via a quick LLM call.

        Args:
            usage: Optional TokenUsage accumulator. If provided, token counts from
                   this LLM call are added to it in-place.

        Returns the parsed dict, or None if inference fails.
        """
        from .utils import aperform_completion_with_backoff

        url_line = f"URL: {url}\n" if url else ""
        prompt = (
            "You are given a data extraction request and a snippet of HTML from a webpage.\n"
            "Your job is to produce a single example JSON object representing ONE item "
            "that the user wants to extract.\n\n"
            "Rules:\n"
            "- Return ONLY a valid JSON object — one flat object, NOT wrapped in an array or outer key.\n"
            "- The object represents a single repeated item (e.g., one product, one article, one row).\n"
            "- Use clean snake_case field names matching the user's description.\n"
            "- If the item has nested repeated sub-items, represent those as an array with one example inside.\n"
            "- Fill values with realistic examples from the HTML so the meaning is clear.\n\n"
            'Example — if the request is "extract product name, price, and reviews":\n'
            '{"name": "Widget Pro", "price": "$29.99", "reviews": [{"author": "Jane", "text": "Great product"}]}\n\n'
            f"{url_line}"
            f"Extraction request: {query}\n\n"
            f"HTML snippet:\n```html\n{html_snippet[:2000]}\n```\n\n"
            "Return ONLY the JSON object for ONE item:"
        )

        try:
            response = await aperform_completion_with_backoff(
                provider=llm_config.provider,
                prompt_with_variables=prompt,
                json_response=True,
                api_token=llm_config.api_token,
                base_url=llm_config.base_url,
            )
            if usage is not None:
                usage.completion_tokens += response.usage.completion_tokens
                usage.prompt_tokens += response.usage.prompt_tokens
                usage.total_tokens += response.usage.total_tokens
            raw = response.choices[0].message.content
            if not raw or not raw.strip():
                return None
            return json.loads(_strip_markdown_fences(raw))
        except Exception:
            return None

    @staticmethod
    def _extract_expected_fields(target_json: dict) -> List[str]:
        """Extract top-level field names from a target JSON example."""
        return list(target_json.keys())

    _GENERATE_SCHEMA_UNWANTED_PROPS = {
        'provider': 'Instead, use llm_config=LLMConfig(provider="...")',
        'api_token': 'Instead, use llm_config=LlMConfig(api_token="...")',
    }

    @staticmethod
    def _build_schema_prompt(html: str, schema_type: str, query: str = None, target_json_example: str = None) -> str:
        """
        Build the prompt for schema generation. Shared by sync and async methods.

        Returns:
            str: Combined system and user prompt
        """
        from .prompts import JSON_SCHEMA_BUILDER

        prompt_template = JSON_SCHEMA_BUILDER if schema_type == "CSS" else JSON_SCHEMA_BUILDER_XPATH

        system_content = f"""You specialize in generating special JSON schemas for web scraping. This schema uses CSS or XPATH selectors to present a repetitive pattern in crawled HTML, such as a product in a product list or a search result item in a list of search results. We use this JSON schema to pass to a language model along with the HTML content to extract structured data from the HTML. The language model uses the JSON schema to extract data from the HTML and retrieve values for fields in the JSON schema, following the schema.

Generating this HTML manually is not feasible, so you need to generate the JSON schema using the HTML content. The HTML copied from the crawled website is provided below, which we believe contains the repetitive pattern.

# Schema main keys:
- name: This is the name of the schema.
- baseSelector: This is the CSS or XPATH selector that identifies the base element that contains all the repetitive patterns.
- baseFields: This is a list of fields that you extract from the base element itself.
- fields: This is a list of fields that you extract from the children of the base element. {{name, selector, type}} based on the type, you may have extra keys such as "attribute" when the type is "attribute".

# Extra Context:
In this context, the following items may or may not be present:
- Example of target JSON object: This is a sample of the final JSON object that we hope to extract from the HTML using the schema you are generating.
- Extra Instructions: This is optional instructions to consider when generating the schema provided by the user.
- Query or explanation of target/goal data item: This is a description of what data we are trying to extract from the HTML. This explanation means we're not sure about the rigid schema of the structures we want, so we leave it to you to use your expertise to create the best and most comprehensive structures aimed at maximizing data extraction from this page. You must ensure that you do not pick up nuances that may exist on a particular page. The focus should be on the data we are extracting, and it must be valid, safe, and robust based on the given HTML.

# What if there is no example of target JSON object and also no extra instructions or even no explanation of target/goal data item?
In this scenario, use your best judgment to generate the schema. You need to examine the content of the page and understand the data it provides. If the page contains repetitive data, such as lists of items, products, jobs, places, books, or movies, focus on one single item that repeats. If the page is a detailed page about one product or item, create a schema to extract the entire structured data. At this stage, you must think and decide for yourself. Try to maximize the number of fields that you can extract from the HTML.

# What are the instructions and details for this schema generation?
{prompt_template}"""

        user_content = f"""
                HTML to analyze:
                ```html
                {html}
                ```
                """

        if query:
            user_content += f"\n\n## Query or explanation of target/goal data item:\n{query}"
        if target_json_example:
            user_content += f"\n\n## Example of target JSON object:\n```json\n{target_json_example}\n```"

        if query and not target_json_example:
            user_content += """IMPORTANT: To remind you, in this process, we are not providing a rigid example of the adjacent objects we seek. We rely on your understanding of the explanation provided in the above section. Make sure to grasp what we are looking for and, based on that, create the best schema.."""
        elif not query and target_json_example:
            user_content += """IMPORTANT: Please remember that in this process, we provided a proper example of a target JSON object. Make sure to adhere to the structure and create a schema that exactly fits this example. If you find that some elements on the page do not match completely, vote for the majority."""
        elif not query and not target_json_example:
            user_content += """IMPORTANT: Since we neither have a query nor an example, it is crucial to rely solely on the HTML content provided. Leverage your expertise to determine the schema based on the repetitive patterns observed in the content."""

        user_content += """IMPORTANT:
        0/ Ensure your schema remains reliable by avoiding selectors that appear to generate dynamically and are not dependable. You want a reliable schema, as it consistently returns the same data even after many page reloads.
        1/ DO NOT USE use base64 kind of classes, they are temporary and not reliable.
        2/ Every selector must refer to only one unique element. You should ensure your selector points to a single element and is unique to the place that contains the information. You have to use available techniques based on CSS or XPATH requested schema to make sure your selector is unique and also not fragile, meaning if we reload the page now or in the future, the selector should remain reliable.
        3/ Do not use Regex as much as possible.

        Analyze the HTML and generate a JSON schema that follows the specified format. Only output valid JSON schema, nothing else.
        """

        return "\n\n".join([system_content, user_content])

    @staticmethod
    def generate_schema(
        html: str = None,
        schema_type: str = "CSS",
        query: str = None,
        target_json_example: str = None,
        llm_config: 'LLMConfig' = create_llm_config(),
        provider: str = None,
        api_token: str = None,
        url: Union[str, List[str]] = None,
        validate: bool = True,
        max_refinements: int = 3,
        usage: 'TokenUsage' = None,
        **kwargs
    ) -> dict:
        """
        Generate extraction schema from HTML content or URL(s) (sync version).

        Args:
            html (str, optional): The HTML content to analyze. If not provided, url must be set.
            schema_type (str): "CSS" or "XPATH". Defaults to "CSS".
            query (str, optional): Natural language description of what data to extract.
            target_json_example (str, optional): Example of desired JSON output.
            llm_config (LLMConfig): LLM configuration object.
            provider (str): Legacy Parameter. LLM provider to use.
            api_token (str): Legacy Parameter. API token for LLM provider.
            url (str or List[str], optional): URL(s) to fetch HTML from. If provided, html parameter is ignored.
                When multiple URLs are provided, HTMLs are fetched in parallel and concatenated.
            validate (bool): If True, validate the schema against the HTML and
                refine via LLM feedback loop. Defaults to False (zero overhead).
            max_refinements (int): Max refinement rounds when validate=True. Defaults to 3.
            usage (TokenUsage, optional): Token usage accumulator. If provided,
                token counts from all LLM calls (including inference and
                validation retries) are added to it in-place.
            **kwargs: Additional args passed to LLM processor.

        Returns:
            dict: Generated schema following the JsonElementExtractionStrategy format.

        Raises:
            ValueError: If neither html nor url is provided.
        """
        import asyncio

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        coro = JsonElementExtractionStrategy.agenerate_schema(
            html=html,
            schema_type=schema_type,
            query=query,
            target_json_example=target_json_example,
            llm_config=llm_config,
            provider=provider,
            api_token=api_token,
            url=url,
            validate=validate,
            max_refinements=max_refinements,
            usage=usage,
            **kwargs
        )

        if loop is None:
            return asyncio.run(coro)
        else:
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(asyncio.run, coro)
                return future.result()

    @staticmethod
    async def agenerate_schema(
        html: str = None,
        schema_type: str = "CSS",
        query: str = None,
        target_json_example: str = None,
        llm_config: 'LLMConfig' = None,
        provider: str = None,
        api_token: str = None,
        url: Union[str, List[str]] = None,
        validate: bool = True,
        max_refinements: int = 3,
        usage: 'TokenUsage' = None,
        **kwargs
    ) -> dict:
        """
        Generate extraction schema from HTML content or URL(s) (async version).

        Use this method when calling from async contexts (e.g., FastAPI) to avoid
        issues with certain LLM providers (e.g., Gemini/Vertex AI) that require
        async execution.

        Args:
            html (str, optional): The HTML content to analyze. If not provided, url must be set.
            schema_type (str): "CSS" or "XPATH". Defaults to "CSS".
            query (str, optional): Natural language description of what data to extract.
            target_json_example (str, optional): Example of desired JSON output.
            llm_config (LLMConfig): LLM configuration object.
            provider (str): Legacy Parameter. LLM provider to use.
            api_token (str): Legacy Parameter. API token for LLM provider.
            url (str or List[str], optional): URL(s) to fetch HTML from. If provided, html parameter is ignored.
                When multiple URLs are provided, HTMLs are fetched in parallel and concatenated.
            validate (bool): If True, validate the schema against the HTML and
                refine via LLM feedback loop. Defaults to False (zero overhead).
            max_refinements (int): Max refinement rounds when validate=True. Defaults to 3.
            usage (TokenUsage, optional): Token usage accumulator. If provided,
                token counts from all LLM calls (including inference and
                validation retries) are added to it in-place.
            **kwargs: Additional args passed to LLM processor.

        Returns:
            dict: Generated schema following the JsonElementExtractionStrategy format.

        Raises:
            ValueError: If neither html nor url is provided.
        """
        from .utils import aperform_completion_with_backoff, preprocess_html_for_schema

        # Validate inputs
        if html is None and (url is None or (isinstance(url, list) and len(url) == 0)):
            raise ValueError("Either 'html' or 'url' must be provided")

        # Check deprecated parameters
        for name, message in JsonElementExtractionStrategy._GENERATE_SCHEMA_UNWANTED_PROPS.items():
            if locals()[name] is not None:
                raise AttributeError(f"Setting '{name}' is deprecated. {message}")

        if llm_config is None:
            llm_config = create_llm_config()

        # Save original HTML(s) before preprocessing (for validation against real HTML)
        original_htmls = []

        # Fetch HTML from URL(s) if provided
        if url is not None:
            from .async_webcrawler import AsyncWebCrawler
            from .async_configs import BrowserConfig, CrawlerRunConfig, CacheMode

            browser_config = BrowserConfig(
                headless=True,
                text_mode=True,
                light_mode=True,
            )
            crawler_config = CrawlerRunConfig(cache_mode=CacheMode.BYPASS)

            # Normalize to list
            urls = [url] if isinstance(url, str) else url

            async with AsyncWebCrawler(config=browser_config) as crawler:
                if len(urls) == 1:
                    result = await crawler.arun(url=urls[0], config=crawler_config)
                    if not result.success:
                        raise Exception(f"Failed to fetch URL '{urls[0]}': {result.error_message}")
                    if result.status_code >= 400:
                        raise Exception(f"HTTP {result.status_code} error for URL '{urls[0]}'")
                    html = result.html
                    original_htmls = [result.html]
                else:
                    results = await crawler.arun_many(urls=urls, config=crawler_config)
                    html_parts = []
                    for i, result in enumerate(results, 1):
                        if not result.success:
                            raise Exception(f"Failed to fetch URL '{result.url}': {result.error_message}")
                        if result.status_code >= 400:
                            raise Exception(f"HTTP {result.status_code} error for URL '{result.url}'")
                        original_htmls.append(result.html)
                        cleaned = preprocess_html_for_schema(
                            html_content=result.html,
                            text_threshold=2000,
                            attr_value_threshold=500,
                            max_size=500_000
                        )
                        header = HTML_EXAMPLE_DELIMITER.format(index=i)
                        html_parts.append(f"{header}\n{cleaned}")
                    html = "\n\n".join(html_parts)
        else:
            original_htmls = [html]

        # Preprocess HTML for schema generation (skip if already preprocessed from multiple URLs)
        if url is None or isinstance(url, str):
            html = preprocess_html_for_schema(
                html_content=html,
                text_threshold=2000,
                attr_value_threshold=500,
                max_size=500_000
            )

        # --- Resolve expected fields for strict validation ---
        expected_fields = None
        if validate:
            if target_json_example:
                # User provided target JSON — extract field names from it
                try:
                    if isinstance(target_json_example, str):
                        target_obj = json.loads(target_json_example)
                    else:
                        target_obj = target_json_example
                    expected_fields = JsonElementExtractionStrategy._extract_expected_fields(target_obj)
                except (json.JSONDecodeError, TypeError):
                    pass
            elif query:
                # No target JSON but query describes fields — infer via quick LLM call
                first_url = None
                if url is not None:
                    first_url = url if isinstance(url, str) else url[0]
                inferred = await JsonElementExtractionStrategy._infer_target_json(
                    query=query, html_snippet=html, llm_config=llm_config, url=first_url, usage=usage
                )
                if inferred:
                    expected_fields = JsonElementExtractionStrategy._extract_expected_fields(inferred)
                    # Also inject as target_json_example for the schema prompt
                    if not target_json_example:
                        target_json_example = json.dumps(inferred, indent=2)

        prompt = JsonElementExtractionStrategy._build_schema_prompt(html, schema_type, query, target_json_example)
        messages = [{"role": "user", "content": prompt}]

        prev_schema_json = None
        last_schema = None
        max_attempts = 1 + (max_refinements if validate else 0)

        for attempt in range(max_attempts):
            try:
                response = await aperform_completion_with_backoff(
                    provider=llm_config.provider,
                    prompt_with_variables=prompt,
                    json_response=True,
                    api_token=llm_config.api_token,
                    base_url=llm_config.base_url,
                    messages=messages,
                    extra_args=kwargs,
                )
                if usage is not None:
                    usage.completion_tokens += response.usage.completion_tokens
                    usage.prompt_tokens += response.usage.prompt_tokens
                    usage.total_tokens += response.usage.total_tokens
                raw = response.choices[0].message.content
                if not raw or not raw.strip():
                    raise ValueError("LLM returned an empty response")

                schema = json.loads(_strip_markdown_fences(raw))
                last_schema = schema
            except json.JSONDecodeError as e:
                # JSON parse failure — ask LLM to fix it
                if not validate or attempt >= max_attempts - 1:
                    raise Exception(f"Failed to parse schema JSON: {str(e)}")
                messages.append({"role": "assistant", "content": raw})
                messages.append({"role": "user", "content": (
                    f"Your response was not valid JSON. Parse error: {e}\n"
                    "Please return ONLY valid JSON, nothing else."
                )})
                continue
            except Exception as e:
                raise Exception(f"Failed to generate schema: {str(e)}")

            # If validation is off, return immediately (zero overhead path)
            if not validate:
                return schema

            # --- Validation feedback loop ---
            # Validate against original HTML(s); success if works on at least one
            best_result = None
            for orig_html in original_htmls:
                vr = JsonElementExtractionStrategy._validate_schema(
                    schema, orig_html, schema_type,
                    expected_fields=expected_fields,
                )
                if best_result is None or vr["populated_fields"] > best_result["populated_fields"]:
                    best_result = vr
                if vr["success"]:
                    break

            if best_result["success"]:
                return schema

            # Last attempt — return best-effort
            if attempt >= max_attempts - 1:
                return schema

            # Detect repeated schema
            current_json = json.dumps(schema, sort_keys=True)
            is_repeated = current_json == prev_schema_json
            prev_schema_json = current_json

            # Build feedback and extend conversation
            feedback = JsonElementExtractionStrategy._build_feedback_message(
                best_result, schema, attempt + 1, is_repeated
            )
            messages.append({"role": "assistant", "content": raw})
            messages.append({"role": "user", "content": feedback})

        # Should not reach here, but return last schema as safety net
        if last_schema is not None:
            return last_schema
        raise Exception("Failed to generate schema: no attempts succeeded")

class JsonCssExtractionStrategy(JsonElementExtractionStrategy):
    """
    Concrete implementation of `JsonElementExtractionStrategy` using CSS selectors.

    How it works:
    1. Parses HTML content with BeautifulSoup.
    2. Selects elements using CSS selectors defined in the schema.
    3. Extracts field data and applies transformations as defined.

    Attributes:
        schema (Dict[str, Any]): The schema defining the extraction rules.
        verbose (bool): Enables verbose logging for debugging purposes.

    Methods:
        _parse_html(html_content): Parses HTML content into a BeautifulSoup object.
        _get_base_elements(parsed_html, selector): Selects base elements using a CSS selector.
        _get_elements(element, selector): Selects child elements using a CSS selector.
        _get_element_text(element): Extracts text content from a BeautifulSoup element.
        _get_element_html(element): Extracts the raw HTML content of a BeautifulSoup element.
        _get_element_attribute(element, attribute): Retrieves an attribute value from a BeautifulSoup element.
    """

    def __init__(self, schema: Dict[str, Any], **kwargs):
        kwargs["input_format"] = "html"  # Force HTML input
        super().__init__(schema, **kwargs)

    def _parse_html(self, html_content: str):
        # return BeautifulSoup(html_content, "html.parser")
        return BeautifulSoup(html_content, "lxml")

    def _get_base_elements(self, parsed_html, selector: str):
        return parsed_html.select(selector)

    def _get_elements(self, element, selector: str):
        # Return all matching elements using select() instead of select_one()
        # This ensures that we get all elements that match the selector, not just the first one
        return element.select(selector)

    def _get_element_text(self, element) -> str:
        return element.get_text(strip=True)

    def _get_element_html(self, element) -> str:
        return str(element)

    def _get_element_attribute(self, element, attribute: str):
        return element.get(attribute)

    def _resolve_source(self, element, source: str):
        source = source.strip()
        if not source.startswith("+"):
            return None
        sel = source[1:].strip()  # e.g. "tr", "tr.subtext", ".classname"
        parts = sel.split(".")
        tag = parts[0].strip() or None
        classes = [p.strip() for p in parts[1:] if p.strip()]
        kwargs = {}
        if classes:
            kwargs["class_"] = lambda c, _cls=classes: c and all(
                cl in c for cl in _cls
            )
        return element.find_next_sibling(tag, **kwargs)

class JsonLxmlExtractionStrategy(JsonElementExtractionStrategy):
    def __init__(self, schema: Dict[str, Any], **kwargs):
        kwargs["input_format"] = "html"
        super().__init__(schema, **kwargs)
        self._selector_cache = {}
        self._xpath_cache = {}
        self._result_cache = {}
        
        # Control selector optimization strategy
        self.use_caching = kwargs.get("use_caching", True)
        self.optimize_common_patterns = kwargs.get("optimize_common_patterns", True)
        
        # Load lxml dependencies once
        from lxml import etree, html
        from lxml.cssselect import CSSSelector
        self.etree = etree
        self.html_parser = html
        self.CSSSelector = CSSSelector
    
    def _parse_html(self, html_content: str):
        """Parse HTML content with error recovery"""
        try:
            parser = self.etree.HTMLParser(recover=True, remove_blank_text=True)
            return self.etree.fromstring(html_content, parser)
        except Exception as e:
            if self.verbose:
                print(f"Error parsing HTML, falling back to alternative method: {e}")
            try:
                return self.html_parser.fromstring(html_content)
            except Exception as e2:
                if self.verbose:
                    print(f"Critical error parsing HTML: {e2}")
                # Create minimal document as fallback
                return self.etree.Element("html")
    
    def _optimize_selector(self, selector_str):
        """Optimize common selector patterns for better performance"""
        if not self.optimize_common_patterns:
            return selector_str
            
        # Handle td:nth-child(N) pattern which is very common in table scraping
        import re
        if re.search(r'td:nth-child\(\d+\)', selector_str):
            return selector_str  # Already handled specially in _apply_selector
            
        # Split complex selectors into parts for optimization
        parts = selector_str.split()
        if len(parts) <= 1:
            return selector_str
            
        # For very long selectors, consider using just the last specific part
        if len(parts) > 3 and any(p.startswith('.') or p.startswith('#') for p in parts):
            specific_parts = [p for p in parts if p.startswith('.') or p.startswith('#')]
            if specific_parts:
                return specific_parts[-1]  # Use most specific class/id selector
                
        return selector_str
    
    def _create_selector_function(self, selector_str):
        """Create a selector function that handles all edge cases"""
        original_selector = selector_str
        
        # Try to optimize the selector if appropriate
        if self.optimize_common_patterns:
            selector_str = self._optimize_selector(selector_str)
        
        try:
            # Attempt to compile the CSS selector
            compiled = self.CSSSelector(selector_str)
            xpath = compiled.path
            
            # Store XPath for later use
            self._xpath_cache[selector_str] = xpath
            
            # Create the wrapper function that implements the selection strategy
            def selector_func(element, context_sensitive=True):
                cache_key = None
                
                # Use result caching if enabled
                if self.use_caching:
                    # Create a cache key based on element and selector
                    element_id = element.get('id', '') or str(hash(element))
                    cache_key = f"{element_id}::{selector_str}"
                    
                    if cache_key in self._result_cache:
                        return self._result_cache[cache_key]
                
                results = []
                try:
                    # Strategy 1: Direct CSS selector application (fastest)
                    results = compiled(element)
                    
                    # If that fails and we need context sensitivity
                    if not results and context_sensitive:
                        # Strategy 2: Try XPath with context adjustment
                        context_xpath = self._make_context_sensitive_xpath(xpath, element)
                        if context_xpath:
                            results = element.xpath(context_xpath)
                        
                        # Strategy 3: Handle special case - nth-child
                        if not results and 'nth-child' in original_selector:
                            results = self._handle_nth_child_selector(element, original_selector)
                        
                        # Strategy 4: Direct descendant search for class/ID selectors
                        if not results:
                            results = self._fallback_class_id_search(element, original_selector)
                            
                        # Strategy 5: Last resort - tag name search for the final part
                        if not results:
                            parts = original_selector.split()
                            if parts:
                                last_part = parts[-1]
                                # Extract tag name from the selector
                                tag_match = re.match(r'^(\w+)', last_part)
                                if tag_match:
                                    tag_name = tag_match.group(1)
                                    results = element.xpath(f".//{tag_name}")
                    
                    # Cache results if caching is enabled
                    if self.use_caching and cache_key:
                        self._result_cache[cache_key] = results
                        
                except Exception as e:
                    if self.verbose:
                        print(f"Error applying selector '{selector_str}': {e}")
                
                return results
                
            return selector_func
            
        except Exception as e:
            if self.verbose:
                print(f"Error compiling selector '{selector_str}': {e}")
            
            # Fallback function for invalid selectors
            return lambda element, context_sensitive=True: []
    
    def _make_context_sensitive_xpath(self, xpath, element):
        """Convert absolute XPath to context-sensitive XPath"""
        try:
            # If starts with descendant-or-self, it's already context-sensitive
            if xpath.startswith('descendant-or-self::'):
                return xpath
                
            # Remove leading slash if present
            if xpath.startswith('/'):
                context_xpath = f".{xpath}"
            else:
                context_xpath = f".//{xpath}"
                
            # Validate the XPath by trying it
            try:
                element.xpath(context_xpath)
                return context_xpath
            except:
                # If that fails, try a simpler descendant search
                return f".//{xpath.split('/')[-1]}"
        except:
            return None
    
    def _handle_nth_child_selector(self, element, selector_str):
        """Special handling for nth-child selectors in tables"""
        import re
        results = []
        
        try:
            # Extract the column number from td:nth-child(N)
            match = re.search(r'td:nth-child\((\d+)\)', selector_str)
            if match:
                col_num = match.group(1)
                
                # Check if there's content after the nth-child part
                remaining_selector = selector_str.split(f"td:nth-child({col_num})", 1)[-1].strip()
                
                if remaining_selector:
                    # If there's a specific element we're looking for after the column
                    # Extract any tag names from the remaining selector
                    tag_match = re.search(r'(\w+)', remaining_selector)
                    tag_name = tag_match.group(1) if tag_match else '*'
                    results = element.xpath(f".//td[{col_num}]//{tag_name}")
                else:
                    # Just get the column cell
                    results = element.xpath(f".//td[{col_num}]")
        except Exception as e:
            if self.verbose:
                print(f"Error handling nth-child selector: {e}")
                
        return results
    
    def _fallback_class_id_search(self, element, selector_str):
        """Fallback to search by class or ID"""
        results = []
        
        try:
            # Extract class selectors (.classname)
            import re
            class_matches = re.findall(r'\.([a-zA-Z0-9_-]+)', selector_str)
            
            # Extract ID selectors (#idname)
            id_matches = re.findall(r'#([a-zA-Z0-9_-]+)', selector_str)
            
            # Try each class
            for class_name in class_matches:
                class_results = element.xpath(f".//*[contains(@class, '{class_name}')]")
                results.extend(class_results)
                
            # Try each ID (usually more specific)
            for id_name in id_matches:
                id_results = element.xpath(f".//*[@id='{id_name}']")
                results.extend(id_results)
        except Exception as e:
            if self.verbose:
                print(f"Error in fallback class/id search: {e}")
                
        return results
    
    def _get_selector(self, selector_str):
        """Get or create a selector function with caching"""
        if selector_str not in self._selector_cache:
            self._selector_cache[selector_str] = self._create_selector_function(selector_str)
        return self._selector_cache[selector_str]
    
    def _get_base_elements(self, parsed_html, selector: str):
        """Get all base elements using the selector"""
        selector_func = self._get_selector(selector)
        # For base elements, we don't need context sensitivity
        return selector_func(parsed_html, context_sensitive=False)
    
    def _get_elements(self, element, selector: str):
        """Get child elements using the selector with context sensitivity"""
        selector_func = self._get_selector(selector)
        return selector_func(element, context_sensitive=True)
    
    def _get_element_text(self, element) -> str:
        """Extract normalized text from element"""
        try:
            # Get all text nodes and normalize
            text = " ".join(t.strip() for t in element.xpath(".//text()") if t.strip())
            return text
        except Exception as e:
            if self.verbose:
                print(f"Error extracting text: {e}")
            # Fallback
            try:
                return element.text_content().strip()
            except:
                return ""
    
    def _get_element_html(self, element) -> str:
        """Get HTML string representation of element"""
        try:
            return self.etree.tostring(element, encoding='unicode', method='html')
        except Exception as e:
            if self.verbose:
                print(f"Error serializing HTML: {e}")
            return ""
    
    def _get_element_attribute(self, element, attribute: str):
        """Get attribute value safely"""
        try:
            return element.get(attribute)
        except Exception as e:
            if self.verbose:
                print(f"Error getting attribute '{attribute}': {e}")
            return None

    def _resolve_source(self, element, source: str):
        source = source.strip()
        if not source.startswith("+"):
            return None
        sel = source[1:].strip()
        parts = sel.split(".")
        tag = parts[0].strip() or "*"
        classes = [p.strip() for p in parts[1:] if p.strip()]
        xpath = f"./following-sibling::{tag}"
        for cls in classes:
            xpath += f"[contains(concat(' ',normalize-space(@class),' '),' {cls} ')]"
        xpath += "[1]"
        results = element.xpath(xpath)
        return results[0] if results else None

    def _clear_caches(self):
        """Clear caches to free memory"""
        if self.use_caching:
            self._result_cache.clear()

class JsonLxmlExtractionStrategy_naive(JsonElementExtractionStrategy):
    def __init__(self, schema: Dict[str, Any], **kwargs):
        kwargs["input_format"] = "html"  # Force HTML input
        super().__init__(schema, **kwargs)
        self._selector_cache = {}
    
    def _parse_html(self, html_content: str):
        from lxml import etree
        parser = etree.HTMLParser(recover=True)
        return etree.fromstring(html_content, parser)
    
    def _get_selector(self, selector_str):
        """Get a selector function that works within the context of an element"""
        if selector_str not in self._selector_cache:
            from lxml.cssselect import CSSSelector
            try:
                # Store both the compiled selector and its xpath translation
                compiled = CSSSelector(selector_str)
                
                # Create a function that will apply this selector appropriately
                def select_func(element):
                    try:
                        # First attempt: direct CSS selector application
                        results = compiled(element)
                        if results:
                            return results
                        
                        # Second attempt: contextual XPath selection
                        # Convert the root-based XPath to a context-based XPath
                        xpath = compiled.path
                        
                        # If the XPath already starts with descendant-or-self, handle it specially
                        if xpath.startswith('descendant-or-self::'):
                            context_xpath = xpath
                        else:
                            # For normal XPath expressions, make them relative to current context
                            context_xpath = f"./{xpath.lstrip('/')}"
                        
                        results = element.xpath(context_xpath)
                        if results:
                            return results
                        
                        # Final fallback: simple descendant search for common patterns
                        if 'nth-child' in selector_str:
                            # Handle td:nth-child(N) pattern
                            import re
                            match = re.search(r'td:nth-child\((\d+)\)', selector_str)
                            if match:
                                col_num = match.group(1)
                                sub_selector = selector_str.split(')', 1)[-1].strip()
                                if sub_selector:
                                    return element.xpath(f".//td[{col_num}]//{sub_selector}")
                                else:
                                    return element.xpath(f".//td[{col_num}]")
                        
                        # Last resort: try each part of the selector separately
                        parts = selector_str.split()
                        if len(parts) > 1 and parts[-1]:
                            return element.xpath(f".//{parts[-1]}")
                            
                        return []
                    except Exception as e:
                        if self.verbose:
                            print(f"Error applying selector '{selector_str}': {e}")
                        return []
                
                self._selector_cache[selector_str] = select_func
            except Exception as e:
                if self.verbose:
                    print(f"Error compiling selector '{selector_str}': {e}")
                
                # Fallback function for invalid selectors
                def fallback_func(element):
                    return []
                
                self._selector_cache[selector_str] = fallback_func
                
        return self._selector_cache[selector_str]
    
    def _get_base_elements(self, parsed_html, selector: str):
        selector_func = self._get_selector(selector)
        return selector_func(parsed_html)
    
    def _get_elements(self, element, selector: str):
        selector_func = self._get_selector(selector)
        return selector_func(element)
    
    def _get_element_text(self, element) -> str:
        return "".join(element.xpath(".//text()")).strip()
    
    def _get_element_html(self, element) -> str:
        from lxml import etree
        return etree.tostring(element, encoding='unicode')
    
    def _get_element_attribute(self, element, attribute: str):
        return element.get(attribute)

    def _resolve_source(self, element, source: str):
        source = source.strip()
        if not source.startswith("+"):
            return None
        sel = source[1:].strip()
        parts = sel.split(".")
        tag = parts[0].strip() or "*"
        classes = [p.strip() for p in parts[1:] if p.strip()]
        xpath = f"./following-sibling::{tag}"
        for cls in classes:
            xpath += f"[contains(concat(' ',normalize-space(@class),' '),' {cls} ')]"
        xpath += "[1]"
        results = element.xpath(xpath)
        return results[0] if results else None

class JsonXPathExtractionStrategy(JsonElementExtractionStrategy):
    """
    Concrete implementation of `JsonElementExtractionStrategy` using XPath selectors.

    How it works:
    1. Parses HTML content into an lxml tree.
    2. Selects elements using XPath expressions.
    3. Converts CSS selectors to XPath when needed.

    Attributes:
        schema (Dict[str, Any]): The schema defining the extraction rules.
        verbose (bool): Enables verbose logging for debugging purposes.

    Methods:
        _parse_html(html_content): Parses HTML content into an lxml tree.
        _get_base_elements(parsed_html, selector): Selects base elements using an XPath selector.
        _css_to_xpath(css_selector): Converts a CSS selector to an XPath expression.
        _get_elements(element, selector): Selects child elements using an XPath selector.
        _get_element_text(element): Extracts text content from an lxml element.
        _get_element_html(element): Extracts the raw HTML content of an lxml element.
        _get_element_attribute(element, attribute): Retrieves an attribute value from an lxml element.
    """

    def __init__(self, schema: Dict[str, Any], **kwargs):
        kwargs["input_format"] = "html"  # Force HTML input
        super().__init__(schema, **kwargs)

    def _parse_html(self, html_content: str):
        return html.fromstring(html_content)

    def _get_base_elements(self, parsed_html, selector: str):
        return parsed_html.xpath(selector)

    def _css_to_xpath(self, css_selector: str) -> str:
        """Convert CSS selector to XPath if needed"""
        if "/" in css_selector:  # Already an XPath
            return css_selector
        return self._basic_css_to_xpath(css_selector)

    def _basic_css_to_xpath(self, css_selector: str) -> str:
        """Basic CSS to XPath conversion for common cases"""
        if " > " in css_selector:
            parts = css_selector.split(" > ")
            return "//" + "/".join(parts)
        if " " in css_selector:
            parts = css_selector.split(" ")
            return "//" + "//".join(parts)
        return "//" + css_selector

    def _get_elements(self, element, selector: str):
        xpath = self._css_to_xpath(selector)
        if not xpath.startswith("."):
            xpath = "." + xpath
        return element.xpath(xpath)

    def _get_element_text(self, element) -> str:
        return "".join(element.xpath(".//text()")).strip()

    def _get_element_html(self, element) -> str:
        return etree.tostring(element, encoding="unicode")

    def _get_element_attribute(self, element, attribute: str):
        return element.get(attribute)

    def _resolve_source(self, element, source: str):
        source = source.strip()
        if not source.startswith("+"):
            return None
        sel = source[1:].strip()
        parts = sel.split(".")
        tag = parts[0].strip() or "*"
        classes = [p.strip() for p in parts[1:] if p.strip()]
        xpath = f"./following-sibling::{tag}"
        for cls in classes:
            xpath += f"[contains(concat(' ',normalize-space(@class),' '),' {cls} ')]"
        xpath += "[1]"
        results = element.xpath(xpath)
        return results[0] if results else None

"""
RegexExtractionStrategy
Fast, zero-LLM extraction of common entities via regular expressions.
"""

_CTRL = {c: rf"\x{ord(c):02x}" for c in map(chr, range(32)) if c not in "\t\n\r"}

_WB_FIX = re.compile(r"\x08")               # stray back-space   →   word-boundary
_NEEDS_ESCAPE = re.compile(r"(?<!\\)\\(?![\\u])")   # lone backslash

def _sanitize_schema(schema: Dict[str, str]) -> Dict[str, str]:
    """Fix common JSON-escape goofs coming from LLMs or manual edits."""
    safe = {}
    for label, pat in schema.items():
        # 1️⃣ replace accidental control chars (inc. the infamous back-space)
        pat = _WB_FIX.sub(r"\\b", pat).translate(_CTRL)

        # 2️⃣ double any single backslash that JSON kept single
        pat = _NEEDS_ESCAPE.sub(r"\\\\", pat)

        # 3️⃣ quick sanity compile
        try:
            re.compile(pat)
        except re.error as e:
            raise ValueError(f"Regex for '{label}' won’t compile after fix: {e}") from None

        safe[label] = pat
    return safe


class RegexExtractionStrategy(ExtractionStrategy):
    """
    A lean strategy that finds e-mails, phones, URLs, dates, money, etc.,
    using nothing but pre-compiled regular expressions.

    Extraction returns::

        {
            "url":   "<page-url>",
            "label": "<pattern-label>",
            "value": "<matched-string>",
            "span":  [start, end]
        }

    Only `generate_schema()` touches an LLM, extraction itself is pure Python.
    """

    # -------------------------------------------------------------- #
    # Built-in patterns exposed as IntFlag so callers can bit-OR them
    # -------------------------------------------------------------- #
    class _B(IntFlag):
        EMAIL           = auto()
        PHONE_INTL      = auto()
        PHONE_US        = auto()
        URL             = auto()
        IPV4            = auto()
        IPV6            = auto()
        UUID            = auto()
        CURRENCY        = auto()
        PERCENTAGE      = auto()
        NUMBER          = auto()
        DATE_ISO        = auto()
        DATE_US         = auto()
        TIME_24H        = auto()
        POSTAL_US       = auto()
        POSTAL_UK       = auto()
        HTML_COLOR_HEX  = auto()
        TWITTER_HANDLE  = auto()
        HASHTAG         = auto()
        MAC_ADDR        = auto()
        IBAN            = auto()
        CREDIT_CARD     = auto()
        NOTHING         = auto()
        ALL             = (
            EMAIL | PHONE_INTL | PHONE_US | URL | IPV4 | IPV6 | UUID
            | CURRENCY | PERCENTAGE | NUMBER | DATE_ISO | DATE_US | TIME_24H
            | POSTAL_US | POSTAL_UK | HTML_COLOR_HEX | TWITTER_HANDLE
            | HASHTAG | MAC_ADDR | IBAN | CREDIT_CARD
        )

    # user-friendly aliases  (RegexExtractionStrategy.Email, .IPv4, …)
    Email          = _B.EMAIL
    PhoneIntl      = _B.PHONE_INTL
    PhoneUS        = _B.PHONE_US
    Url            = _B.URL
    IPv4           = _B.IPV4
    IPv6           = _B.IPV6
    Uuid           = _B.UUID
    Currency       = _B.CURRENCY
    Percentage     = _B.PERCENTAGE
    Number         = _B.NUMBER
    DateIso        = _B.DATE_ISO
    DateUS         = _B.DATE_US
    Time24h        = _B.TIME_24H
    PostalUS       = _B.POSTAL_US
    PostalUK       = _B.POSTAL_UK
    HexColor       = _B.HTML_COLOR_HEX
    TwitterHandle  = _B.TWITTER_HANDLE
    Hashtag        = _B.HASHTAG
    MacAddr        = _B.MAC_ADDR
    Iban           = _B.IBAN
    CreditCard     = _B.CREDIT_CARD
    All            = _B.ALL
    Nothing        = _B(0)  # no patterns

    # ------------------------------------------------------------------ #
    # Built-in pattern catalog
    # ------------------------------------------------------------------ #
    DEFAULT_PATTERNS: Dict[str, str] = {
        # Communication
        "email":           r"[\w.+-]+@[\w-]+\.[\w.-]+",
        "phone_intl":      r"\+?\d[\d .()-]{7,}\d",
        "phone_us":        r"\(?\d{3}\)?[ -. ]?\d{3}[ -. ]?\d{4}",
        # Web
        "url":             r"https?://[^\s\"'<>]+",
        "ipv4":            r"(?:\d{1,3}\.){3}\d{1,3}",
        "ipv6":            r"[A-F0-9]{1,4}(?::[A-F0-9]{1,4}){7}",
        # IDs
        "uuid":            r"[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}",
        # Money / numbers
        "currency":        r"(?:USD|EUR|RM|\$|€|£)\s?\d+(?:[.,]\d{2})?",
        "percentage":      r"\d+(?:\.\d+)?%",
        "number":          r"\b\d{1,3}(?:[,.\s]\d{3})*(?:\.\d+)?\b",
        # Dates / Times
        "date_iso":        r"\d{4}-\d{2}-\d{2}",
        "date_us":         r"\d{1,2}/\d{1,2}/\d{2,4}",
        "time_24h":        r"\b(?:[01]?\d|2[0-3]):[0-5]\d(?:[:.][0-5]\d)?\b",
        # Misc
        "postal_us":       r"\b\d{5}(?:-\d{4})?\b",
        "postal_uk":       r"\b[A-Z]{1,2}\d[A-Z\d]? ?\d[A-Z]{2}\b",
        "html_color_hex":  r"#[0-9A-Fa-f]{6}\b",
        "twitter_handle":  r"@[\w]{1,15}",
        "hashtag":         r"#[\w-]+",
        "mac_addr":        r"(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}",
        "iban":            r"[A-Z]{2}\d{2}[A-Z0-9]{11,30}",
        "credit_card":     r"\b(?:4\d{12}(?:\d{3})?|5[1-5]\d{14}|3[47]\d{13}|6(?:011|5\d{2})\d{12})\b",
    }

    _FLAGS = re.IGNORECASE | re.MULTILINE
    _UNWANTED_PROPS = {
        "provider": "Use llm_config instead",
        "api_token": "Use llm_config instead",
    }

    # ------------------------------------------------------------------ #
    # Construction
    # ------------------------------------------------------------------ #
    def __init__(
        self,
        pattern: "_B" = _B.NOTHING,
        *,
        custom: Optional[Union[Dict[str, str], List[Tuple[str, str]]]] = None,
        input_format: str = "fit_html",
        **kwargs,
    ) -> None:
        """
        Args:
            patterns: Custom patterns overriding or extending defaults.
                      Dict[label, regex] or list[tuple(label, regex)].
            input_format: "html", "markdown" or "text".
            **kwargs: Forwarded to ExtractionStrategy.
        """
        super().__init__(input_format=input_format, **kwargs)

        # 1️⃣  take only the requested built-ins
        merged: Dict[str, str] = {
            key: rx
            for key, rx in self.DEFAULT_PATTERNS.items()
            if getattr(self._B, key.upper()).value & pattern
        }

        # 2️⃣  apply user overrides / additions
        if custom:
            if isinstance(custom, dict):
                merged.update(custom)
            else:  # iterable of (label, regex)
                merged.update({lbl: rx for lbl, rx in custom})

        self._compiled: Dict[str, Pattern] = {
            lbl: re.compile(rx, self._FLAGS) for lbl, rx in merged.items()
        }

    # ------------------------------------------------------------------ #
    # Extraction
    # ------------------------------------------------------------------ #
    def extract(self, url: str, content: str, *q, **kw) -> List[Dict[str, Any]]:
        # text = self._plain_text(html)
        out: List[Dict[str, Any]] = []

        for label, cre in self._compiled.items():
            for m in cre.finditer(content):
                out.append(
                    {
                        "url": url,
                        "label": label,
                        "value": m.group(0),
                        "span": [m.start(), m.end()],
                    }
                )
        return out

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    def _plain_text(self, content: str) -> str:
        if self.input_format == "text":
            return content
        return BeautifulSoup(content, "lxml").get_text(" ", strip=True)

    # ------------------------------------------------------------------ #
    # LLM-assisted pattern generator
    # ------------------------------------------------------------------ #
    # ------------------------------------------------------------------ #
    # LLM-assisted one-off pattern builder
    # ------------------------------------------------------------------ #
    @staticmethod
    def generate_pattern(
        label: str,
        html: str,
        *,
        query: Optional[str] = None,
        examples: Optional[List[str]] = None,
        llm_config: Optional[LLMConfig] = None,
        **kwargs,
    ) -> Dict[str, str]:
        """
        Ask an LLM for a single page-specific regex and return
            {label: pattern}   ── ready for RegexExtractionStrategy(custom=…)
        """

        # ── guard deprecated kwargs
        for k in RegexExtractionStrategy._UNWANTED_PROPS:
            if k in kwargs:
                raise AttributeError(
                    f"{k} is deprecated, {RegexExtractionStrategy._UNWANTED_PROPS[k]}"
                )

        # ── default LLM config
        if llm_config is None:
            llm_config = create_llm_config()

        # ── system prompt – hardened
        system_msg = (
            "You are an expert Python-regex engineer.\n"
            f"Return **one** JSON object whose single key is exactly \"{label}\", "
            "and whose value is a raw-string regex pattern that works with "
            "the standard `re` module in Python.\n\n"
            "Strict rules (obey every bullet):\n"
            "• If a *user query* is supplied, treat it as the precise semantic target and optimise the "
            "  pattern to capture ONLY text that answers that query. If the query conflicts with the "
            "  sample HTML, the HTML wins.\n"
            "• Tailor the pattern to the *sample HTML* – reproduce its exact punctuation, spacing, "
            "  symbols, capitalisation, etc. Do **NOT** invent a generic form.\n"
            "• Keep it minimal and fast: avoid unnecessary capturing, prefer non-capturing `(?: … )`, "
            "  and guard against catastrophic backtracking.\n"
            "• Anchor with `^`, `$`, or `\\b` only when it genuinely improves precision.\n"
            "• Use inline flags like `(?i)` when needed; no verbose flag comments.\n"
            "• Output must be valid JSON – no markdown, code fences, comments, or extra keys.\n"
            "• The regex value must be a Python string literal: **double every backslash** "
            "(e.g. `\\\\b`, `\\\\d`, `\\\\\\\\`).\n\n"
            "Example valid output:\n"
            f"{{\"{label}\": \"(?:RM|rm)\\\\s?\\\\d{{1,3}}(?:,\\\\d{{3}})*(?:\\\\.\\\\d{{2}})?\"}}"
        )

        # ── user message: cropped HTML + optional hints
        user_parts = ["```html", html[:5000], "```"]  # protect token budget
        if query:
            user_parts.append(f"\n\n## Query\n{query.strip()}")
        if examples:
            user_parts.append("## Examples\n" + "\n".join(examples[:20]))
        user_msg = "\n\n".join(user_parts)

        # ── LLM call (with retry/backoff)
        resp = perform_completion_with_backoff(
            provider=llm_config.provider,
            prompt_with_variables="\n\n".join([system_msg, user_msg]),
            json_response=True,
            api_token=llm_config.api_token,
            base_url=llm_config.base_url,
            extra_args=kwargs,
        )

        # ── clean & load JSON (fix common escape mistakes *before* json.loads)
        raw = resp.choices[0].message.content
        raw = raw.replace("\x08", "\\b")                     # stray back-space → \b
        raw = re.sub(r'(?<!\\)\\(?![\\u"])', r"\\\\", raw)   # lone \ → \\

        try:
            pattern_dict = json.loads(raw)
        except Exception as exc:
            raise ValueError(f"LLM did not return valid JSON: {raw}") from exc

        # quick sanity-compile
        for lbl, pat in pattern_dict.items():
            try:
                re.compile(pat)
            except re.error as e:
                raise ValueError(f"Invalid regex for '{lbl}': {e}") from None

        return pattern_dict

```


## File: crawl4ai/models.py


```py
from pydantic import BaseModel, HttpUrl, PrivateAttr, Field, ConfigDict, BeforeValidator
from typing import Annotated
from typing import List, Dict, Optional, Callable, Awaitable, Union, Any
from typing import AsyncGenerator
from typing import Generic, TypeVar
from enum import Enum
from dataclasses import dataclass
from .ssl_certificate import SSLCertificate
from datetime import datetime
from datetime import timedelta


###############################
# Dispatcher Models
###############################
@dataclass
class DomainState:
    last_request_time: float = 0
    current_delay: float = 0
    fail_count: int = 0


@dataclass
class CrawlerTaskResult:
    task_id: str
    url: str
    result: "CrawlResult"
    memory_usage: float
    peak_memory: float
    start_time: Union[datetime, float]
    end_time: Union[datetime, float]
    error_message: str = ""
    retry_count: int = 0
    wait_time: float = 0.0
    
    @property
    def success(self) -> bool:
        return self.result.success

class CrawlStatus(Enum):
    QUEUED = "QUEUED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"

@dataclass
class CrawlStats:
    task_id: str
    url: str
    status: CrawlStatus
    start_time: Optional[Union[datetime, float]] = None
    end_time: Optional[Union[datetime, float]] = None
    memory_usage: float = 0.0
    peak_memory: float = 0.0
    error_message: str = ""
    wait_time: float = 0.0
    retry_count: int = 0
    counted_requeue: bool = False

    @property
    def duration(self) -> str:
        if not self.start_time:
            return "0:00"
            
        # Convert start_time to datetime if it's a float
        start = self.start_time
        if isinstance(start, float):
            start = datetime.fromtimestamp(start)
            
        # Get end time or use current time
        end = self.end_time or datetime.now()
        # Convert end_time to datetime if it's a float
        if isinstance(end, float):
            end = datetime.fromtimestamp(end)
            
        duration = end - start
        return str(timedelta(seconds=int(duration.total_seconds())))

class DisplayMode(Enum):
    DETAILED = "DETAILED"
    AGGREGATED = "AGGREGATED"


###############################
# Crawler Models
###############################
@dataclass
class TokenUsage:
    completion_tokens: int = 0
    prompt_tokens: int = 0
    total_tokens: int = 0
    completion_tokens_details: Optional[dict] = None
    prompt_tokens_details: Optional[dict] = None

class UrlModel(BaseModel):
    url: HttpUrl
    forced: bool = False



@dataclass
class TraversalStats:
    """Statistics for the traversal process"""

    start_time: datetime = datetime.now()
    urls_processed: int = 0
    urls_failed: int = 0
    urls_skipped: int = 0
    total_depth_reached: int = 0
    current_depth: int = 0

class DispatchResult(BaseModel):
    task_id: str
    memory_usage: float
    peak_memory: float
    start_time: Union[datetime, float]
    end_time: Union[datetime, float]
    error_message: str = ""

class MarkdownGenerationResult(BaseModel):
    raw_markdown: str
    markdown_with_citations: str
    references_markdown: str
    fit_markdown: Optional[str] = None
    fit_html: Optional[str] = None

    def __str__(self):
        return self.raw_markdown
    
class CrawlResult(BaseModel):
    url: str
    html: str
    fit_html: Optional[str] = None
    success: bool
    cleaned_html: Optional[str] = None
    media: Dict[str, List[Dict]] = {}
    links: Dict[str, List[Dict]] = {}
    downloaded_files: Optional[List[str]] = None
    js_execution_result: Optional[Dict[str, Any]] = None
    screenshot: Optional[str] = None
    pdf: Optional[bytes] = None
    mhtml: Optional[str] = None
    _markdown: Optional[MarkdownGenerationResult] = PrivateAttr(default=None)
    extracted_content: Optional[str] = None
    metadata: Optional[dict] = None
    error_message: Optional[str] = None
    session_id: Optional[str] = None
    response_headers: Optional[dict] = None
    status_code: Optional[int] = None
    ssl_certificate: Optional[SSLCertificate] = None
    dispatch_result: Optional[DispatchResult] = None
    redirected_url: Optional[str] = None
    redirected_status_code: Optional[int] = None
    network_requests: Optional[List[Dict[str, Any]]] = None
    console_messages: Optional[List[Dict[str, Any]]] = None
    tables: List[Dict] = Field(default_factory=list)  # NEW – [{headers,rows,caption,summary}]
    # Cache validation metadata (Smart Cache)
    head_fingerprint: Optional[str] = None
    cached_at: Optional[float] = None
    cache_status: Optional[str] = None  # "hit", "hit_validated", "hit_fallback", "miss"
    # Anti-bot retry/proxy usage stats
    crawl_stats: Optional[Dict[str, Any]] = None

    model_config = ConfigDict(arbitrary_types_allowed=True)

# NOTE: The StringCompatibleMarkdown class, custom __init__ method, property getters/setters,
# and model_dump override all exist to support a smooth transition from markdown as a string
# to markdown as a MarkdownGenerationResult object, while maintaining backward compatibility.
# 
# This allows code that expects markdown to be a string to continue working, while also
# providing access to the full MarkdownGenerationResult object's properties.
# 
# The markdown_v2 property is deprecated and raises an error directing users to use markdown.
# 
# When backward compatibility is no longer needed in future versions, this entire mechanism
# can be simplified to a standard field with no custom accessors or serialization logic.
    
    def __init__(self, **data):
        markdown_result = data.pop('markdown', None)
        super().__init__(**data)
        if markdown_result is not None:
            self._markdown = (
                MarkdownGenerationResult(**markdown_result)
                if isinstance(markdown_result, dict)
                else markdown_result
            )
    
    @property
    def markdown(self):
        """
        Property that returns a StringCompatibleMarkdown object that behaves like
        a string but also provides access to MarkdownGenerationResult attributes.
        
        This approach allows backward compatibility with code that expects 'markdown'
        to be a string, while providing access to the full MarkdownGenerationResult.
        """
        if self._markdown is None:
            return None
        return StringCompatibleMarkdown(self._markdown)
    
    @markdown.setter
    def markdown(self, value):
        """
        Setter for the markdown property.
        """
        self._markdown = value
    
    @property
    def markdown_v2(self):
        """
        Deprecated property that raises an AttributeError when accessed.

        This property exists to inform users that 'markdown_v2' has been
        deprecated and they should use 'markdown' instead.
        """
        raise AttributeError(
            "The 'markdown_v2' attribute is deprecated and has been removed. "
            """Please use 'markdown' instead, which now returns a MarkdownGenerationResult, with
            following properties:
            - raw_markdown: The raw markdown string
            - markdown_with_citations: The markdown string with citations
            - references_markdown: The markdown string with references
            - fit_markdown: The markdown string with fit text
            """
        )
    
    @property
    def fit_markdown(self):
        """
        Deprecated property that raises an AttributeError when accessed.
        """
        raise AttributeError(
            "The 'fit_markdown' attribute is deprecated and has been removed. "
            "Please use 'markdown.fit_markdown' instead."
        )
    
    @property
    def fit_html(self):
        """
        Deprecated property that raises an AttributeError when accessed.
        """
        raise AttributeError(
            "The 'fit_html' attribute is deprecated and has been removed. "
            "Please use 'markdown.fit_html' instead."
        )

    def model_dump(self, *args, **kwargs):
        """
        Override model_dump to include the _markdown private attribute in serialization.
        
        This override is necessary because:
        1. PrivateAttr fields are excluded from serialization by default
        2. We need to maintain backward compatibility by including the 'markdown' field
           in the serialized output
        3. We're transitioning from 'markdown_v2' to enhancing 'markdown' to hold
           the same type of data
        
        Future developers: This method ensures that the markdown content is properly
        serialized despite being stored in a private attribute. If the serialization
        requirements change, this is where you would update the logic.
        """
        result = super().model_dump(*args, **kwargs)
        
        # Remove any property descriptors that might have been included
        # These deprecated properties should not be in the serialized output
        for key in ['fit_html', 'fit_markdown', 'markdown_v2']:
            if key in result and isinstance(result[key], property):
                # del result[key]
                # Nasrin: I decided to convert it to string instead of removing it.
                result[key] = str(result[key])
        
        # Add the markdown field properly
        if self._markdown is not None:
            result["markdown"] = self._markdown.model_dump() 
        return result

class StringCompatibleMarkdown(str):
    """A string subclass that also provides access to MarkdownGenerationResult attributes"""
    def __new__(cls, markdown_result):
        return super().__new__(cls, markdown_result.raw_markdown)
    
    def __init__(self, markdown_result):
        self._markdown_result = markdown_result
    
    def __getattr__(self, name):
        return getattr(self._markdown_result, name)

CrawlResultT = TypeVar('CrawlResultT', bound=CrawlResult)

class CrawlResultContainer(Generic[CrawlResultT]):
    def __init__(self, results: Union[CrawlResultT, List[CrawlResultT]]):
        # Normalize to a list
        if isinstance(results, list):
            self._results = results
        else:
            self._results = [results]

    def __iter__(self):
        return iter(self._results)

    async def __aiter__(self):
        for item in self._results:
            yield item

    def __getitem__(self, index):
        return self._results[index]

    def __len__(self):
        return len(self._results)

    def __getattr__(self, attr):
        # Delegate attribute access to the first element.
        if self._results:
            return getattr(self._results[0], attr)
        raise AttributeError(f"{self.__class__.__name__} object has no attribute '{attr}'")

    def __repr__(self):
        return f"{self.__class__.__name__}({self._results!r})"

RunManyReturn = Union[
    CrawlResultContainer[CrawlResultT],
    AsyncGenerator[CrawlResultT, None]
]


# END of backward compatibility code for markdown/markdown_v2.
# When removing this code in the future, make sure to:
# 1. Replace the private attribute and property with a standard field
# 2. Update any serialization logic that might depend on the current behavior

class AsyncCrawlResponse(BaseModel):
    html: str
    response_headers: Dict[str, str]
    js_execution_result: Optional[Dict[str, Any]] = None
    status_code: int
    screenshot: Optional[str] = None
    pdf_data: Optional[bytes] = None
    mhtml_data: Optional[str] = None
    get_delayed_content: Optional[Callable[[Optional[float]], Awaitable[str]]] = None
    downloaded_files: Optional[List[str]] = None
    ssl_certificate: Optional[SSLCertificate] = None
    redirected_url: Optional[str] = None
    redirected_status_code: Optional[int] = None
    network_requests: Optional[List[Dict[str, Any]]] = None
    console_messages: Optional[List[Dict[str, Any]]] = None

    model_config = ConfigDict(arbitrary_types_allowed=True)

###############################
# Scraping Models
###############################
def _coerce_int(v):
    """Coerce to int or return None for non-numeric values like '100%' or 'auto'."""
    if v is None:
        return None
    try:
        return int(v)
    except (ValueError, TypeError):
        return None

class MediaItem(BaseModel):
    src: Optional[str] = ""
    data: Optional[str] = ""
    alt: Optional[str] = ""
    desc: Optional[str] = ""
    score: Optional[int] = 0
    type: str = "image"
    group_id: Optional[int] = 0
    format: Optional[str] = None
    width: Annotated[Optional[int], BeforeValidator(_coerce_int)] = None


class Link(BaseModel):
    href: Optional[str] = ""
    text: Optional[str] = ""
    title: Optional[str] = ""
    base_domain: Optional[str] = ""
    head_data: Optional[Dict[str, Any]] = None  # Head metadata extracted from link target
    head_extraction_status: Optional[str] = None  # "success", "failed", "skipped"
    head_extraction_error: Optional[str] = None  # Error message if extraction failed
    intrinsic_score: Optional[float] = None  # Quality score based on URL structure, text, and context
    contextual_score: Optional[float] = None  # BM25 relevance score based on query and head content
    total_score: Optional[float] = None  # Combined score from intrinsic and contextual scores


class Media(BaseModel):
    images: List[MediaItem] = []
    videos: List[
        MediaItem
    ] = []  # Using MediaItem model for now, can be extended with Video model if needed
    audios: List[
        MediaItem
    ] = []  # Using MediaItem model for now, can be extended with Audio model if needed
    tables: List[Dict] = []  # Table data extracted from HTML tables


class Links(BaseModel):
    internal: List[Link] = []
    external: List[Link] = []


class ScrapingResult(BaseModel):
    cleaned_html: str
    success: bool
    media: Media = Media()
    links: Links = Links()
    metadata: Dict[str, Any] = {}

```


## File: crawl4ai/content_filter_strategy.py


```py
import inspect
import re
import time
from bs4 import BeautifulSoup, Tag
from typing import List, Tuple, Dict, Optional
from rank_bm25 import BM25Okapi
from collections import deque
from bs4 import NavigableString, Comment

from .utils import (
    clean_tokens,
    perform_completion_with_backoff,
    escape_json_string,
    sanitize_html,
    get_home_folder,
    extract_xml_data,
    merge_chunks,
)
from .types import LLMConfig
from .config import DEFAULT_PROVIDER, OVERLAP_RATE, WORD_TOKEN_RATE
from abc import ABC, abstractmethod
import math
from snowballstemmer import stemmer
from .models import TokenUsage
from .prompts import PROMPT_FILTER_CONTENT
import json
import hashlib
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from .async_logger import AsyncLogger, LogLevel, LogColor


class RelevantContentFilter(ABC):
    """Abstract base class for content filtering strategies"""

    def __init__(
        self,
        user_query: str = None,
        verbose: bool = False,
        logger: Optional[AsyncLogger] = None,
    ):
        """
        Initializes the RelevantContentFilter class with optional user query.

        Args:
            user_query (str): User query for filtering (optional).
            verbose (bool): Enable verbose logging (default: False).
        """
        self.user_query = user_query
        self.included_tags = {
            # Primary structure
            "article",
            "main",
            "section",
            "div",
            # List structures
            "ul",
            "ol",
            "li",
            "dl",
            "dt",
            "dd",
            # Text content
            "p",
            "span",
            "blockquote",
            "pre",
            "code",
            # Headers
            "h1",
            "h2",
            "h3",
            "h4",
            "h5",
            "h6",
            # Tables
            "table",
            "thead",
            "tbody",
            "tr",
            "td",
            "th",
            # Other semantic elements
            "figure",
            "figcaption",
            "details",
            "summary",
            # Text formatting
            "em",
            "strong",
            "b",
            "i",
            "mark",
            "small",
            # Rich content
            "time",
            "address",
            "cite",
            "q",
        }
        self.excluded_tags = {
            "nav",
            "footer",
            "header",
            "aside",
            "script",
            "style",
            "form",
            "iframe",
            "noscript",
        }
        self.header_tags = {"h1", "h2", "h3", "h4", "h5", "h6"}
        self.negative_patterns = re.compile(
            r"nav|footer|header|sidebar|ads|comment|promo|advert|social|share", re.I
        )
        self.min_word_count = 2
        self.verbose = False
        self.logger = logger

    @abstractmethod
    def filter_content(self, html: str) -> List[str]:
        """Abstract method to be implemented by specific filtering strategies"""
        pass

    def extract_page_query(self, soup: BeautifulSoup, body: Tag) -> str:
        """Common method to extract page metadata with fallbacks"""
        if self.user_query:
            return self.user_query

        query_parts = []

        # Title
        try:
            title = soup.title.string
            if title:
                query_parts.append(title)
        except Exception:
            pass

        if soup.find("h1"):
            query_parts.append(soup.find("h1").get_text())

        # Meta tags
        temp = ""
        for meta_name in ["keywords", "description"]:
            meta = soup.find("meta", attrs={"name": meta_name})
            if meta and meta.get("content"):
                query_parts.append(meta["content"])
                temp += meta["content"]

        # If still empty, grab first significant paragraph
        if not temp:
            # Find the first tag P thatits text contains more than 50 characters
            for p in body.find_all("p"):
                if len(p.get_text()) > 150:
                    query_parts.append(p.get_text()[:150])
                    break

        return " ".join(filter(None, query_parts))

    def extract_text_chunks(
        self, body: Tag, min_word_threshold: int = None
    ) -> List[Tuple[str, str]]:
        """
        Extracts text chunks from a BeautifulSoup body element while preserving order.
        Returns list of tuples (text, tag_name) for classification.

        Args:
            body: BeautifulSoup Tag object representing the body element

        Returns:
            List of (text, tag_name) tuples
        """
        # Tags to ignore - inline elements that shouldn't break text flow
        INLINE_TAGS = {
            "a",
            "abbr",
            "acronym",
            "b",
            "bdo",
            "big",
            "br",
            "button",
            "cite",
            "code",
            "dfn",
            "em",
            "i",
            "img",
            "input",
            "kbd",
            "label",
            "map",
            "object",
            "q",
            "samp",
            "script",
            "select",
            "small",
            "span",
            "strong",
            "sub",
            "sup",
            "textarea",
            "time",
            "tt",
            "var",
        }

        # Tags that typically contain meaningful headers
        HEADER_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6", "header"}

        chunks = []
        current_text = []
        chunk_index = 0

        def should_break_chunk(tag: Tag) -> bool:
            """Determine if a tag should cause a break in the current text chunk"""
            return tag.name not in INLINE_TAGS and not (
                tag.name == "p" and len(current_text) == 0
            )

        # Use deque for efficient push/pop operations
        stack = deque([(body, False)])

        while stack:
            element, visited = stack.pop()

            if visited:
                # End of block element - flush accumulated text
                if current_text and should_break_chunk(element):
                    text = " ".join("".join(current_text).split())
                    if text:
                        tag_type = (
                            "header" if element.name in HEADER_TAGS else "content"
                        )
                        chunks.append((chunk_index, text, tag_type, element))
                        chunk_index += 1
                    current_text = []
                continue

            if isinstance(element, NavigableString):
                if str(element).strip():
                    current_text.append(str(element).strip())
                continue

            # Pre-allocate children to avoid multiple list operations
            children = list(element.children)
            if not children:
                continue

            # Mark block for revisit after processing children
            stack.append((element, True))

            # Add children in reverse order for correct processing
            for child in reversed(children):
                if isinstance(child, (Tag, NavigableString)):
                    stack.append((child, False))

        # Handle any remaining text
        if current_text:
            text = " ".join("".join(current_text).split())
            if text:
                chunks.append((chunk_index, text, "content", body))

        if min_word_threshold:
            chunks = [
                chunk for chunk in chunks if len(chunk[1].split()) >= min_word_threshold
            ]

        return chunks

    def _deprecated_extract_text_chunks(
        self, soup: BeautifulSoup
    ) -> List[Tuple[int, str, Tag]]:
        """Common method for extracting text chunks"""
        _text_cache = {}

        def fast_text(element: Tag) -> str:
            elem_id = id(element)
            if elem_id in _text_cache:
                return _text_cache[elem_id]
            texts = []
            for content in element.contents:
                if isinstance(content, str):
                    text = content.strip()
                    if text:
                        texts.append(text)
            result = " ".join(texts)
            _text_cache[elem_id] = result
            return result

        candidates = []
        index = 0

        def dfs(element):
            nonlocal index
            if isinstance(element, Tag):
                if element.name in self.included_tags:
                    if not self.is_excluded(element):
                        text = fast_text(element)
                        word_count = len(text.split())

                        # Headers pass through with adjusted minimum
                        if element.name in self.header_tags:
                            if word_count >= 3:  # Minimal sanity check for headers
                                candidates.append((index, text, element))
                                index += 1
                        # Regular content uses standard minimum
                        elif word_count >= self.min_word_count:
                            candidates.append((index, text, element))
                            index += 1

                for child in element.children:
                    dfs(child)

        dfs(soup.body if soup.body else soup)
        return candidates

    def is_excluded(self, tag: Tag) -> bool:
        """Common method for exclusion logic"""
        if tag.name in self.excluded_tags:
            return True
        class_id = " ".join(
            filter(None, [" ".join(tag.get("class", [])), tag.get("id", "")])
        )
        return bool(self.negative_patterns.search(class_id))

    def clean_element(self, tag: Tag) -> str:
        """Common method for cleaning HTML elements with minimal overhead"""
        if not tag or not isinstance(tag, Tag):
            return ""

        unwanted_tags = {"script", "style", "aside", "form", "iframe", "noscript"}
        unwanted_attrs = {
            "style",
            "onclick",
            "onmouseover",
            "align",
            "bgcolor",
            "class",
            "id",
        }

        # Use string builder pattern for better performance
        builder = []

        def render_tag(elem):
            if not isinstance(elem, Tag):
                if isinstance(elem, str):
                    builder.append(elem.strip())
                return

            if elem.name in unwanted_tags:
                return

            # Start tag
            builder.append(f"<{elem.name}")

            # Add cleaned attributes
            attrs = {k: v for k, v in elem.attrs.items() if k not in unwanted_attrs}
            for key, value in attrs.items():
                builder.append(f' {key}="{value}"')

            builder.append(">")

            # Process children
            for child in elem.children:
                render_tag(child)

            # Close tag
            builder.append(f"</{elem.name}>")

        try:
            render_tag(tag)
            return "".join(builder)
        except Exception:
            return str(tag)  # Fallback to original if anything fails


class BM25ContentFilter(RelevantContentFilter):
    """
    Content filtering using BM25 algorithm with priority tag handling.

    How it works:
    1. Extracts page metadata with fallbacks.
    2. Extracts text chunks from the body element.
    3. Tokenizes the corpus and query.
    4. Applies BM25 algorithm to calculate scores for each chunk.
    5. Filters out chunks below the threshold.
    6. Sorts chunks by score in descending order.
    7. Returns the top N chunks.

    Attributes:
        user_query (str): User query for filtering (optional).
        bm25_threshold (float): BM25 threshold for filtering (default: 1.0).
        language (str): Language for stemming (default: 'english').

        Methods:
            filter_content(self, html: str, min_word_threshold: int = None)
    """

    def __init__(
        self,
        user_query: str = None,
        bm25_threshold: float = 1.0,
        language: str = "english",
        use_stemming: bool = True,
    ):
        """
        Initializes the BM25ContentFilter class, if not provided, falls back to page metadata.

        Note:
        If no query is given and no page metadata is available, then it tries to pick up the first significant paragraph.

        Args:
            user_query (str): User query for filtering (optional).
            bm25_threshold (float): BM25 threshold for filtering (default: 1.0).
            language (str): Language for stemming (default: 'english').
            use_stemming (bool): Whether to apply stemming (default: True).
        """
        super().__init__(user_query=user_query)
        self.bm25_threshold = bm25_threshold
        self.use_stemming = use_stemming
        self.priority_tags = {
            "h1": 5.0,
            "h2": 4.0,
            "h3": 3.0,
            "title": 4.0,
            "strong": 2.0,
            "b": 1.5,
            "em": 1.5,
            "blockquote": 2.0,
            "code": 2.0,
            "pre": 1.5,
            "th": 1.5,  # Table headers
        }
        self.stemmer = stemmer(language) if use_stemming else None

    def filter_content(self, html: str, min_word_threshold: int = None) -> List[str]:
        """
        Implements content filtering using BM25 algorithm with priority tag handling.

            Note:
        This method implements the filtering logic for the BM25ContentFilter class.
        It takes HTML content as input and returns a list of filtered text chunks.

        Args:
            html (str): HTML content to be filtered.
            min_word_threshold (int): Minimum word threshold for filtering (optional).

        Returns:
            List[str]: List of filtered text chunks.
        """
        if not html or not isinstance(html, str):
            return []

        soup = BeautifulSoup(html, "lxml")

        # Check if body is present
        if not soup.body:
            # Wrap in body tag if missing
            soup = BeautifulSoup(f"<body>{html}</body>", "lxml")
        body = soup.find("body")

        query = self.extract_page_query(soup, body)

        if not query:
            return []
            # return [self.clean_element(soup)]

        candidates = self.extract_text_chunks(body, min_word_threshold)

        if not candidates:
            return []

        # Tokenize corpus
        # tokenized_corpus = [chunk.lower().split() for _, chunk, _, _ in candidates]
        # tokenized_query = query.lower().split()

        # tokenized_corpus = [[ps.stem(word) for word in chunk.lower().split()]
        #                 for _, chunk, _, _ in candidates]
        # tokenized_query = [ps.stem(word) for word in query.lower().split()]

        if self.use_stemming:
            tokenized_corpus = [
                [self.stemmer.stemWord(word) for word in chunk.lower().split()]
                for _, chunk, _, _ in candidates
            ]
            tokenized_query = [
                self.stemmer.stemWord(word) for word in query.lower().split()
            ]
        else:
            tokenized_corpus = [
                chunk.lower().split() for _, chunk, _, _ in candidates
            ]
            tokenized_query = query.lower().split()

        # tokenized_corpus = [[self.stemmer.stemWord(word) for word in tokenize_text(chunk.lower())]
        #            for _, chunk, _, _ in candidates]
        # tokenized_query = [self.stemmer.stemWord(word) for word in tokenize_text(query.lower())]

        # Clean from stop words and noise
        tokenized_corpus = [clean_tokens(tokens) for tokens in tokenized_corpus]
        tokenized_query = clean_tokens(tokenized_query)

        bm25 = BM25Okapi(tokenized_corpus)
        scores = bm25.get_scores(tokenized_query)

        # Adjust scores with tag weights
        adjusted_candidates = []
        for score, (index, chunk, tag_type, tag) in zip(scores, candidates):
            tag_weight = self.priority_tags.get(tag.name, 1.0)
            adjusted_score = score * tag_weight
            adjusted_candidates.append((adjusted_score, index, chunk, tag))

        # Filter candidates by threshold
        selected_candidates = [
            (index, chunk, tag)
            for adjusted_score, index, chunk, tag in adjusted_candidates
            if adjusted_score >= self.bm25_threshold
        ]

        if not selected_candidates:
            return []

        # Sort selected candidates by original document order
        selected_candidates.sort(key=lambda x: x[0])

        # Deduplicate by chunk text, keeping first occurrence (lowest index)
        seen_texts = set()
        unique_candidates = []
        for index, chunk, tag in selected_candidates:
            if chunk not in seen_texts:
                seen_texts.add(chunk)
                unique_candidates.append((index, chunk, tag))

        return [self.clean_element(tag) for _, _, tag in unique_candidates]


class PruningContentFilter(RelevantContentFilter):
    """
    Content filtering using pruning algorithm with dynamic threshold.

    How it works:
    1. Extracts page metadata with fallbacks.
    2. Extracts text chunks from the body element.
    3. Applies pruning algorithm to calculate scores for each chunk.
    4. Filters out chunks below the threshold.
    5. Sorts chunks by score in descending order.
    6. Returns the top N chunks.

    Attributes:
        user_query (str): User query for filtering (optional), if not provided, falls back to page metadata.
        min_word_threshold (int): Minimum word threshold for filtering (optional).
        threshold_type (str): Threshold type for dynamic threshold (default: 'fixed').
        threshold (float): Fixed threshold value (default: 0.48).

        Methods:
            filter_content(self, html: str, min_word_threshold: int = None):
    """

    def __init__(
        self,
        user_query: str = None,
        min_word_threshold: int = None,
        threshold_type: str = "fixed",
        threshold: float = 0.48,
    ):
        """
        Initializes the PruningContentFilter class, if not provided, falls back to page metadata.

        Note:
        If no query is given and no page metadata is available, then it tries to pick up the first significant paragraph.

        Args:
            user_query (str): User query for filtering (optional).
            min_word_threshold (int): Minimum word threshold for filtering (optional).
            threshold_type (str): Threshold type for dynamic threshold (default: 'fixed').
            threshold (float): Fixed threshold value (default: 0.48).
        """
        super().__init__(None)
        self.min_word_threshold = min_word_threshold
        self.threshold_type = threshold_type
        self.threshold = threshold

        # Add tag importance for dynamic threshold
        self.tag_importance = {
            "article": 1.5,
            "main": 1.4,
            "section": 1.3,
            "p": 1.2,
            "h1": 1.4,
            "h2": 1.3,
            "h3": 1.2,
            "div": 0.7,
            "span": 0.6,
        }

        # Metric configuration
        self.metric_config = {
            "text_density": True,
            "link_density": True,
            "tag_weight": True,
            "class_id_weight": True,
            "text_length": True,
        }

        self.metric_weights = {
            "text_density": 0.4,
            "link_density": 0.2,
            "tag_weight": 0.2,
            "class_id_weight": 0.1,
            "text_length": 0.1,
        }

        self.tag_weights = {
            "div": 0.5,
            "p": 1.0,
            "article": 1.5,
            "section": 1.0,
            "span": 0.3,
            "li": 0.5,
            "ul": 0.5,
            "ol": 0.5,
            "h1": 1.2,
            "h2": 1.1,
            "h3": 1.0,
            "h4": 0.9,
            "h5": 0.8,
            "h6": 0.7,
        }

    def filter_content(self, html: str, min_word_threshold: int = None) -> List[str]:
        """
        Implements content filtering using pruning algorithm with dynamic threshold.

        Note:
        This method implements the filtering logic for the PruningContentFilter class.
        It takes HTML content as input and returns a list of filtered text chunks.

        Args:
            html (str): HTML content to be filtered.
            min_word_threshold (int): Minimum word threshold for filtering (optional).

        Returns:
            List[str]: List of filtered text chunks.
        """
        if not html or not isinstance(html, str):
            return []

        soup = BeautifulSoup(html, "lxml")
        if not soup.body:
            soup = BeautifulSoup(f"<body>{html}</body>", "lxml")

        # Remove comments and unwanted tags
        self._remove_comments(soup)
        self._remove_unwanted_tags(soup)

        # Prune tree starting from body
        body = soup.find("body")
        self._prune_tree(body)

        # Extract remaining content as list of HTML strings
        content_blocks = []
        for element in body.children:
            if isinstance(element, str) or not hasattr(element, "name"):
                continue
            if len(element.get_text(strip=True)) > 0:
                content_blocks.append(str(element))

        return content_blocks

    def _remove_comments(self, soup):
        """Removes HTML comments"""
        for element in soup(string=lambda string: isinstance(string, Comment)):
            element.extract()

    def _remove_unwanted_tags(self, soup):
        """Removes unwanted tags"""
        for tag in self.excluded_tags:
            for element in soup.find_all(tag):
                element.decompose()

    def _prune_tree(self, node):
        """
        Prunes the tree starting from the given node.

        Args:
            node (Tag): The node from which the pruning starts.
        """
        if not node or not hasattr(node, "name") or node.name is None:
            return

        text_len = len(node.get_text(strip=True))
        tag_len = len(node.encode_contents().decode("utf-8"))
        link_text_len = sum(
            len(s.strip())
            for s in (a.string for a in node.find_all("a", recursive=False))
            if s
        )

        metrics = {
            "node": node,
            "tag_name": node.name,
            "text_len": text_len,
            "tag_len": tag_len,
            "link_text_len": link_text_len,
        }

        score = self._compute_composite_score(metrics, text_len, tag_len, link_text_len)

        if self.threshold_type == "fixed":
            should_remove = score < self.threshold
        else:  # dynamic
            tag_importance = self.tag_importance.get(node.name, 0.7)
            text_ratio = text_len / tag_len if tag_len > 0 else 0
            link_ratio = link_text_len / text_len if text_len > 0 else 1

            threshold = self.threshold  # base threshold
            if tag_importance > 1:
                threshold *= 0.8
            if text_ratio > 0.4:
                threshold *= 0.9
            if link_ratio > 0.6:
                threshold *= 1.2

            should_remove = score < threshold

        if should_remove:
            node.decompose()
        else:
            children = [child for child in node.children if hasattr(child, "name")]
            for child in children:
                self._prune_tree(child)

    def _compute_composite_score(self, metrics, text_len, tag_len, link_text_len):
        """Computes the composite score"""
        if self.min_word_threshold:
            # Get raw text from metrics node - avoid extra processing
            text = metrics["node"].get_text(strip=True)
            word_count = text.count(" ") + 1
            if word_count < self.min_word_threshold:
                return -1.0  # Guaranteed removal
        score = 0.0
        total_weight = 0.0

        if self.metric_config["text_density"]:
            density = text_len / tag_len if tag_len > 0 else 0
            score += self.metric_weights["text_density"] * density
            total_weight += self.metric_weights["text_density"]

        if self.metric_config["link_density"]:
            density = 1 - (link_text_len / text_len if text_len > 0 else 0)
            score += self.metric_weights["link_density"] * density
            total_weight += self.metric_weights["link_density"]

        if self.metric_config["tag_weight"]:
            tag_score = self.tag_weights.get(metrics["tag_name"], 0.5)
            score += self.metric_weights["tag_weight"] * tag_score
            total_weight += self.metric_weights["tag_weight"]

        if self.metric_config["class_id_weight"]:
            class_score = self._compute_class_id_weight(metrics["node"])
            score += self.metric_weights["class_id_weight"] * max(0, class_score)
            total_weight += self.metric_weights["class_id_weight"]

        if self.metric_config["text_length"]:
            score += self.metric_weights["text_length"] * math.log(text_len + 1)
            total_weight += self.metric_weights["text_length"]

        return score / total_weight if total_weight > 0 else 0

    def _compute_class_id_weight(self, node):
        """Computes the class ID weight"""
        class_id_score = 0
        if "class" in node.attrs:
            classes = " ".join(node["class"])
            if self.negative_patterns.match(classes):
                class_id_score -= 0.5
        if "id" in node.attrs:
            element_id = node["id"]
            if self.negative_patterns.match(element_id):
                class_id_score -= 0.5
        return class_id_score


class LLMContentFilter(RelevantContentFilter):
    """Content filtering using LLMs to generate relevant markdown.

    How it works:
    1. Extracts page metadata with fallbacks.
    2. Extracts text chunks from the body element.
    3. Applies LLMs to generate markdown for each chunk.
    4. Filters out chunks below the threshold.
    5. Sorts chunks by score in descending order.
    6. Returns the top N chunks.

    Attributes:
        llm_config (LLMConfig): LLM configuration object.
        instruction (str): Instruction for LLM markdown generation
        chunk_token_threshold (int): Chunk token threshold for splitting (default: 1e9).
        overlap_rate (float): Overlap rate for chunking (default: 0.5).
        word_token_rate (float): Word token rate for chunking (default: 0.2).
        verbose (bool): Enable verbose logging (default: False).
        logger (AsyncLogger): Custom logger for LLM operations (optional).
    """
    _UNWANTED_PROPS = {
        'provider' : 'Instead, use llm_config=LLMConfig(provider="...")',
        'api_token' : 'Instead, use llm_config=LlMConfig(api_token="...")',
        'base_url' : 'Instead, use llm_config=LLMConfig(base_url="...")',
        'api_base' : 'Instead, use llm_config=LLMConfig(base_url="...")',
    }

    def __init__(
        self,
        llm_config: "LLMConfig" = None,
        instruction: str = None,
        chunk_token_threshold: int = int(1e9),
        overlap_rate: float = OVERLAP_RATE,
        word_token_rate: float = WORD_TOKEN_RATE,
        # char_token_rate: float = WORD_TOKEN_RATE * 5,
        # chunk_mode: str = "char",
        verbose: bool = False,
        logger: Optional[AsyncLogger] = None,
        ignore_cache: bool = True,
        # Deprecated properties
        provider: str = DEFAULT_PROVIDER,
        api_token: Optional[str] = None,
        base_url: Optional[str] = None,
        api_base: Optional[str] = None,
        extra_args: Dict = None,
    ):
        super().__init__(None)
        self.provider = provider
        self.api_token = api_token
        self.base_url = base_url or api_base
        self.llm_config = llm_config
        self.instruction = instruction
        self.chunk_token_threshold = chunk_token_threshold
        self.overlap_rate = overlap_rate
        self.word_token_rate = word_token_rate or WORD_TOKEN_RATE
        # self.chunk_mode: str = chunk_mode
        # self.char_token_rate = char_token_rate or word_token_rate / 5
        # self.token_rate = word_token_rate if chunk_mode == "word" else self.char_token_rate
        self.token_rate = word_token_rate or WORD_TOKEN_RATE
        self.extra_args = extra_args or {}
        self.ignore_cache = ignore_cache
        self.verbose = verbose

        # Setup logger with custom styling for LLM operations
        if logger:
            self.logger = logger
        elif verbose:
            self.logger = AsyncLogger(
                verbose=verbose,
                icons={
                    **AsyncLogger.DEFAULT_ICONS,
                    "LLM": "★",  # Star for LLM operations
                    "CHUNK": "◈",  # Diamond for chunks
                    "CACHE": "⚡",  # Lightning for cache operations
                },
                colors={
                    **AsyncLogger.DEFAULT_COLORS,
                    LogLevel.INFO: LogColor.DIM_MAGENTA  # Dimmed purple for LLM ops
                },
            )
        else:
            self.logger = None

        self.usages = []
        self.total_usage = TokenUsage()
    
    def __setattr__(self, name, value):
        """Handle attribute setting."""
        # TODO: Planning to set properties dynamically based on the __init__ signature
        sig = inspect.signature(self.__init__)
        all_params = sig.parameters  # Dictionary of parameter names and their details

        if name in self._UNWANTED_PROPS and value is not all_params[name].default:
            raise AttributeError(f"Setting '{name}' is deprecated. {self._UNWANTED_PROPS[name]}")
        
        super().__setattr__(name, value)  
        
    def _get_cache_key(self, html: str, instruction: str) -> str:
        """Generate a unique cache key based on HTML and instruction"""
        content = f"{html}{instruction}"
        return hashlib.md5(content.encode()).hexdigest()

    def _merge_chunks(self, text: str) -> List[str]:
        """Split text into chunks with overlap using char or word mode."""
        ov = int(self.chunk_token_threshold * self.overlap_rate)
        sections = merge_chunks(
            docs=[text],
            target_size=self.chunk_token_threshold,
            overlap=ov,
            word_token_ratio=self.word_token_rate,
        )
        return sections

    def filter_content(self, html: str, ignore_cache: bool = True) -> List[str]:
        if not html or not isinstance(html, str):
            return []

        if self.logger:
            self.logger.info(
                "Starting LLM markdown content filtering process",
                tag="LLM",
                params={"provider": self.llm_config.provider},
                colors={"provider": LogColor.CYAN},
            )

        # Cache handling
        cache_dir = Path(get_home_folder()) / "llm_cache" / "content_filter"
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache_key = self._get_cache_key(html, self.instruction or "")
        cache_file = cache_dir / f"{cache_key}.json"

        # if ignore_cache == None:
        ignore_cache = self.ignore_cache

        if not ignore_cache and cache_file.exists():
            if self.logger:
                self.logger.info("Found  cached markdown result", tag="CACHE")
            try:
                with cache_file.open("r") as f:
                    cached_data = json.load(f)
                    usage = TokenUsage(**cached_data["usage"])
                    self.usages.append(usage)
                    self.total_usage.completion_tokens += usage.completion_tokens
                    self.total_usage.prompt_tokens += usage.prompt_tokens
                    self.total_usage.total_tokens += usage.total_tokens
                    return cached_data["blocks"]
            except Exception as e:
                if self.logger:
                    self.logger.error(
                        f"LLM markdown: Cache read error: {str(e)}", tag="CACHE"
                    )

        # Split into chunks
        html_chunks = self._merge_chunks(html)
        if self.logger:
            self.logger.info(
                "LLM markdown: Split content into {chunk_count} chunks",
                tag="CHUNK",
                params={"chunk_count": len(html_chunks)},
                colors={"chunk_count": LogColor.YELLOW},
            )

        start_time = time.time()

        # Process chunks in parallel
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = []
            for i, chunk in enumerate(html_chunks):
                if self.logger:
                    self.logger.debug(
                        "LLM markdown: Processing chunk {chunk_num}/{total_chunks}",
                        tag="CHUNK",
                        params={"chunk_num": i + 1, "total_chunks": len(html_chunks)},
                    )

                prompt_variables = {
                    "HTML": escape_json_string(sanitize_html(chunk)),
                    "REQUEST": self.instruction
                    or "Convert this HTML into clean, relevant markdown, removing any noise or irrelevant content.",
                }

                prompt = PROMPT_FILTER_CONTENT
                for var, value in prompt_variables.items():
                    prompt = prompt.replace("{" + var + "}", value)

                def _proceed_with_chunk(
                    provider: str,
                    prompt: str,
                    api_token: str,
                    base_url: Optional[str] = None,
                    extra_args: Dict = {},
                ) -> List[str]:
                    if self.logger:
                        self.logger.info(
                            "LLM Markdown: Processing chunk {chunk_num}",
                            tag="CHUNK",
                            params={"chunk_num": i + 1},
                        )
                    return perform_completion_with_backoff(
                        provider,
                        prompt,
                        api_token,
                        base_url=base_url,
                        base_delay=self.llm_config.backoff_base_delay,
                        max_attempts=self.llm_config.backoff_max_attempts,
                        exponential_factor=self.llm_config.backoff_exponential_factor,
                        extra_args=extra_args,
                    )

                future = executor.submit(
                    _proceed_with_chunk,
                    self.llm_config.provider,
                    prompt,
                    self.llm_config.api_token,
                    self.llm_config.base_url,
                    self.extra_args,
                )
                futures.append((i, future))

            # Collect results in order
            ordered_results = []
            for i, future in sorted(futures):
                try:
                    response = future.result()

                    # Track usage
                    usage = TokenUsage(
                        completion_tokens=response.usage.completion_tokens,
                        prompt_tokens=response.usage.prompt_tokens,
                        total_tokens=response.usage.total_tokens,
                        completion_tokens_details=(
                            response.usage.completion_tokens_details.__dict__
                            if response.usage.completion_tokens_details
                            else {}
                        ),
                        prompt_tokens_details=(
                            response.usage.prompt_tokens_details.__dict__
                            if response.usage.prompt_tokens_details
                            else {}
                        ),
                    )
                    self.usages.append(usage)
                    self.total_usage.completion_tokens += usage.completion_tokens
                    self.total_usage.prompt_tokens += usage.prompt_tokens
                    self.total_usage.total_tokens += usage.total_tokens

                    blocks = extract_xml_data(
                        ["content"], response.choices[0].message.content
                    )["content"]
                    if blocks:
                        ordered_results.append(blocks)
                        if self.logger:
                            self.logger.success(
                                "LLM markdown: Successfully processed chunk {chunk_num}",
                                tag="CHUNK",
                                params={"chunk_num": i + 1},
                            )
                except Exception as e:
                    if self.logger:
                        self.logger.error(
                            "LLM markdown: Error processing chunk {chunk_num}: {error}",
                            tag="CHUNK",
                            params={"chunk_num": i + 1, "error": str(e)},
                        )

        end_time = time.time()
        if self.logger:
            self.logger.success(
                "LLM markdown: Completed processing in {time:.2f}s",
                tag="LLM",
                params={"time": end_time - start_time},
                colors={"time": LogColor.YELLOW},
            )

        result = ordered_results if ordered_results else []

        # Cache the final result
        cache_data = {"blocks": result, "usage": self.total_usage.__dict__}
        with cache_file.open("w") as f:
            json.dump(cache_data, f)
            if self.logger:
                self.logger.info("Cached results for future use", tag="CACHE")

        return result

    def show_usage(self) -> None:
        """Print usage statistics"""
        print("\n=== Token Usage Summary ===")
        print(f"{'Type':<15} {'Count':>12}")
        print("-" * 30)
        print(f"{'Completion':<15} {self.total_usage.completion_tokens:>12,}")
        print(f"{'Prompt':<15} {self.total_usage.prompt_tokens:>12,}")
        print(f"{'Total':<15} {self.total_usage.total_tokens:>12,}")

        if self.usages:
            print("\n=== Usage History ===")
            print(f"{'Request #':<10} {'Completion':>12} {'Prompt':>12} {'Total':>12}")
            print("-" * 48)
            for i, usage in enumerate(self.usages, 1):
                print(
                    f"{i:<10} {usage.completion_tokens:>12,} "
                    f"{usage.prompt_tokens:>12,} {usage.total_tokens:>12,}"
                )

```


## File: crawl4ai/markdown_generation_strategy.py


```py
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, Tuple
from .models import MarkdownGenerationResult
from .html2text import CustomHTML2Text
# from .types import RelevantContentFilter
from .content_filter_strategy import RelevantContentFilter
import re
from urllib.parse import urljoin

# Pre-compile the regex pattern
LINK_PATTERN = re.compile(r'!?\[((?:[^\[\]]|\[(?:[^\[\]]|\[[^\]]*\])*\])*)\]\(((?:[^()\s]|\([^()]*\))*)(?:\s+"([^"]*)")?\)')


def fast_urljoin(base: str, url: str) -> str:
    """Fast URL joining for common cases."""
    if url.startswith(("http://", "https://", "mailto:", "//")):
        return url
    if url.startswith("/"):
        # Handle absolute paths
        if base.endswith("/"):
            return base[:-1] + url
        return base + url
    return urljoin(base, url)


class MarkdownGenerationStrategy(ABC):
    """Abstract base class for markdown generation strategies."""

    def __init__(
        self,
        content_filter: Optional[RelevantContentFilter] = None,
        options: Optional[Dict[str, Any]] = None,
        verbose: bool = False,
        content_source: str = "cleaned_html",
    ):
        self.content_filter = content_filter
        self.options = options or {}
        self.verbose = verbose
        self.content_source = content_source

    @abstractmethod
    def generate_markdown(
        self,
        input_html: str,
        base_url: str = "",
        html2text_options: Optional[Dict[str, Any]] = None,
        content_filter: Optional[RelevantContentFilter] = None,
        citations: bool = True,
        **kwargs,
    ) -> MarkdownGenerationResult:
        """Generate markdown from the selected input HTML."""
        pass


class DefaultMarkdownGenerator(MarkdownGenerationStrategy):
    """
    Default implementation of markdown generation strategy.

    How it works:
    1. Generate raw markdown from cleaned HTML.
    2. Convert links to citations.
    3. Generate fit markdown if content filter is provided.
    4. Return MarkdownGenerationResult.

    Args:
        content_filter (Optional[RelevantContentFilter]): Content filter for generating fit markdown.
        options (Optional[Dict[str, Any]]): Additional options for markdown generation. Defaults to None.
        content_source (str): Source of content to generate markdown from. Options: "cleaned_html", "raw_html", "fit_html". Defaults to "cleaned_html".

    Returns:
        MarkdownGenerationResult: Result containing raw markdown, fit markdown, fit HTML, and references markdown.
    """

    def __init__(
        self,
        content_filter: Optional[RelevantContentFilter] = None,
        options: Optional[Dict[str, Any]] = None,
        content_source: str = "cleaned_html",
    ):
        super().__init__(content_filter, options, verbose=False, content_source=content_source)

    def convert_links_to_citations(
        self, markdown: str, base_url: str = ""
    ) -> Tuple[str, str]:
        """
        Convert links in markdown to citations.

        How it works:
        1. Find all links in the markdown.
        2. Convert links to citations.
        3. Return converted markdown and references markdown.

        Note:
        This function uses a regex pattern to find links in markdown.

        Args:
            markdown (str): Markdown text.
            base_url (str): Base URL for URL joins.

        Returns:
            Tuple[str, str]: Converted markdown and references markdown.
        """
        link_map = {}
        url_cache = {}  # Cache for URL joins
        parts = []
        last_end = 0
        counter = 1

        for match in LINK_PATTERN.finditer(markdown):
            parts.append(markdown[last_end : match.start()])
            text, url, title = match.groups()

            # Use cached URL if available, otherwise compute and cache
            if base_url and not url.startswith(("http://", "https://", "mailto:")):
                if url not in url_cache:
                    url_cache[url] = fast_urljoin(base_url, url)
                url = url_cache[url]

            if url not in link_map:
                desc = []
                if title:
                    desc.append(title)
                if text and text != title:
                    desc.append(text)
                link_map[url] = (counter, ": " + " - ".join(desc) if desc else "")
                counter += 1

            num = link_map[url][0]
            parts.append(
                f"{text}⟨{num}⟩"
                if not match.group(0).startswith("!")
                else f"![{text}⟨{num}⟩]"
            )
            last_end = match.end()

        parts.append(markdown[last_end:])
        converted_text = "".join(parts)

        # Pre-build reference strings
        references = ["\n\n## References\n\n"]
        references.extend(
            f"⟨{num}⟩ {url}{desc}\n"
            for url, (num, desc) in sorted(link_map.items(), key=lambda x: x[1][0])
        )

        return converted_text, "".join(references)

    def generate_markdown(
        self,
        input_html: str,
        base_url: str = "",
        html2text_options: Optional[Dict[str, Any]] = None,
        options: Optional[Dict[str, Any]] = None,
        content_filter: Optional[RelevantContentFilter] = None,
        citations: bool = True,
        **kwargs,
    ) -> MarkdownGenerationResult:
        """
        Generate markdown with citations from the provided input HTML.

        How it works:
        1. Generate raw markdown from the input HTML.
        2. Convert links to citations.
        3. Generate fit markdown if content filter is provided.
        4. Return MarkdownGenerationResult.

        Args:
            input_html (str): The HTML content to process (selected based on content_source).
            base_url (str): Base URL for URL joins.
            html2text_options (Optional[Dict[str, Any]]): HTML2Text options.
            options (Optional[Dict[str, Any]]): Additional options for markdown generation.
            content_filter (Optional[RelevantContentFilter]): Content filter for generating fit markdown.
            citations (bool): Whether to generate citations.

        Returns:
            MarkdownGenerationResult: Result containing raw markdown, fit markdown, fit HTML, and references markdown.
        """
        try:
            # Initialize HTML2Text with default options for better conversion
            h = CustomHTML2Text(baseurl=base_url)
            default_options = {
                "body_width": 0,  # Disable text wrapping
                "ignore_emphasis": False,
                "ignore_links": False,
                "ignore_images": False,
                "protect_links": False,
                "single_line_break": True,
                "mark_code": True,
                "escape_snob": False,
            }

            # Update with custom options if provided
            if html2text_options:
                default_options.update(html2text_options)
            elif options:
                default_options.update(options)
            elif self.options:
                default_options.update(self.options)

            h.update_params(**default_options)

            # Ensure we have valid input
            if not input_html:
                input_html = ""
            elif not isinstance(input_html, str):
                input_html = str(input_html)

            # Generate raw markdown
            try:
                raw_markdown = h.handle(input_html)
            except Exception as e:
                raw_markdown = f"Error converting HTML to markdown: {str(e)}"

            raw_markdown = raw_markdown.replace("    ```", "```")

            # Convert links to citations
            markdown_with_citations: str = raw_markdown
            references_markdown: str = ""
            if citations:
                try:
                    (
                        markdown_with_citations,
                        references_markdown,
                    ) = self.convert_links_to_citations(raw_markdown, base_url)
                except Exception as e:
                    markdown_with_citations = raw_markdown
                    references_markdown = f"Error generating citations: {str(e)}"

            # Generate fit markdown if content filter is provided
            fit_markdown: Optional[str] = ""
            filtered_html: Optional[str] = ""
            if content_filter or self.content_filter:
                try:
                    content_filter = content_filter or self.content_filter
                    filtered_html = content_filter.filter_content(input_html)
                    filtered_html = "\n".join(
                        "<div>{}</div>".format(s) for s in filtered_html
                    )
                    fit_markdown = h.handle(filtered_html)
                except Exception as e:
                    fit_markdown = f"Error generating fit markdown: {str(e)}"
                    filtered_html = ""

            return MarkdownGenerationResult(
                raw_markdown=raw_markdown or "",
                markdown_with_citations=markdown_with_citations or "",
                references_markdown=references_markdown or "",
                fit_markdown=fit_markdown or "",
                fit_html=filtered_html or "",
            )
        except Exception as e:
            # If anything fails, return empty strings with error message
            error_msg = f"Error in markdown generation: {str(e)}"
            return MarkdownGenerationResult(
                raw_markdown=error_msg,
                markdown_with_citations=error_msg,
                references_markdown="",
                fit_markdown="",
                fit_html="",
            )

```


## File: crawl4ai/browser_manager.py


```py
import asyncio
import time
from typing import Dict, List, Optional, Tuple
import os
import sys
import shutil
import tempfile
import psutil  
import signal
import subprocess
import shlex
from playwright.async_api import BrowserContext
import hashlib
from .js_snippet import load_js_script
from .config import DOWNLOAD_PAGE_TIMEOUT
from .async_configs import BrowserConfig, CrawlerRunConfig
from .utils import get_chromium_path
import warnings


BROWSER_DISABLE_OPTIONS = [
    "--disable-background-networking",
    "--disable-background-timer-throttling",
    "--disable-backgrounding-occluded-windows",
    "--disable-breakpad",
    "--disable-client-side-phishing-detection",
    "--disable-component-extensions-with-background-pages",
    "--disable-default-apps",
    "--disable-extensions",
    "--disable-features=TranslateUI",
    "--disable-hang-monitor",
    "--disable-ipc-flooding-protection",
    "--disable-popup-blocking",
    "--disable-prompt-on-repost",
    "--disable-sync",
    "--force-color-profile=srgb",
    "--metrics-recording-only",
    "--no-first-run",
    "--password-store=basic",
    "--use-mock-keychain",
]


class ManagedBrowser:
    """
    Manages the browser process and context. This class allows to connect to the browser using CDP protocol.

    Attributes:
        browser_type (str): The type of browser to launch. Supported values: "chromium", "firefox", "webkit".
                            Default: "chromium".
        user_data_dir (str or None): Path to a user data directory for persistent sessions. If None, a
                                     temporary directory may be used. Default: None.
        headless (bool): Whether to run the browser in headless mode (no visible GUI).
                         Default: True.
        browser_process (subprocess.Popen): The process object for the browser.
        temp_dir (str): Temporary directory for user data if not provided.
        debugging_port (int): Port for debugging the browser.
        host (str): Host for debugging the browser.

        Methods:
            start(): Starts the browser process and returns the CDP endpoint URL.
            _get_browser_path(): Returns the browser executable path based on OS and browser type.
            _get_browser_args(): Returns browser-specific command line arguments.
            _get_user_data_dir(): Returns the user data directory path.
            _cleanup(): Terminates the browser process and removes the temporary directory.
            create_profile(): Static method to create a user profile by launching a browser for user interaction.
    """
    
    @staticmethod
    def build_browser_flags(config: BrowserConfig) -> List[str]:
        """Common CLI flags for launching Chromium"""
        flags = [
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-infobars",
            "--window-position=0,0",
            "--ignore-certificate-errors",
            "--ignore-certificate-errors-spki-list",
            "--disable-blink-features=AutomationControlled",
            "--window-position=400,0",
            "--disable-renderer-backgrounding",
            "--disable-ipc-flooding-protection",
            "--force-color-profile=srgb",
            "--mute-audio",
            "--disable-background-timer-throttling",
            # Memory-saving flags: disable unused Chrome features
            "--disable-features=OptimizationHints,MediaRouter,DialMediaRouteProvider",
            "--disable-component-update",
            "--disable-domain-reliability",
        ]
        # GPU flags disable WebGL which anti-bot sensors detect as headless.
        # Keep WebGL working (via SwiftShader) when stealth mode is active.
        if not config.enable_stealth:
            flags.extend([
                "--disable-gpu",
                "--disable-gpu-compositing",
                "--disable-software-rasterizer",
            ])
        if config.memory_saving_mode:
            flags.extend([
                "--aggressive-cache-discard",
                '--js-flags=--max-old-space-size=512',
            ])
        if config.light_mode:
            flags.extend(BROWSER_DISABLE_OPTIONS)
        if config.text_mode:
            flags.extend([
                "--blink-settings=imagesEnabled=false",
                "--disable-remote-fonts",
                "--disable-images",
                "--disable-javascript",
                "--disable-software-rasterizer",
                "--disable-dev-shm-usage",
            ])
        # proxy support — only pass server URL, never credentials.
        # Chromium's --proxy-server flag silently ignores inline user:pass@.
        # Auth credentials are handled at the Playwright context level instead.
        if config.proxy:
            flags.append(f"--proxy-server={config.proxy}")
        elif config.proxy_config:
            flags.append(f"--proxy-server={config.proxy_config.server}")
        # dedupe
        return list(dict.fromkeys(flags))

    browser_type: str
    user_data_dir: str
    headless: bool
    browser_process: subprocess.Popen
    temp_dir: str
    debugging_port: int
    host: str

    def __init__(
        self,
        browser_type: str = "chromium",
        user_data_dir: Optional[str] = None,
        headless: bool = False,
        logger=None,
        host: str = "localhost",
        debugging_port: int = 9222,
        cdp_url: Optional[str] = None, 
        browser_config: Optional[BrowserConfig] = None,
    ):
        """
        Initialize the ManagedBrowser instance.

        Args:
            browser_type (str): The type of browser to launch. Supported values: "chromium", "firefox", "webkit".
                                Default: "chromium".
            user_data_dir (str or None): Path to a user data directory for persistent sessions. If None, a
                                         temporary directory may be used. Default: None.
            headless (bool): Whether to run the browser in headless mode (no visible GUI).
                             Default: True.
            logger (logging.Logger): Logger instance for logging messages. Default: None.
            host (str): Host for debugging the browser. Default: "localhost".
            debugging_port (int): Port for debugging the browser. Default: 9222.
            cdp_url (str or None): CDP URL to connect to the browser. Default: None.
            browser_config (BrowserConfig): Configuration object containing all browser settings. Default: None.
        """
        self.browser_type = browser_config.browser_type
        self.user_data_dir = browser_config.user_data_dir
        self.headless = browser_config.headless
        self.browser_process = None
        self.temp_dir = None
        self.debugging_port = browser_config.debugging_port
        self.host = browser_config.host
        self.logger = logger
        self.shutting_down = False
        self.cdp_url = browser_config.cdp_url
        self.browser_config = browser_config

    async def start(self) -> str:
        """
        Starts the browser process or returns CDP endpoint URL.
        If cdp_url is provided, returns it directly.
        If user_data_dir is not provided for local browser, creates a temporary directory.
        
        Returns:
            str: CDP endpoint URL
        """
        # If CDP URL provided, just return it
        if self.cdp_url:
            return self.cdp_url

        # Create temp dir if needed
        if not self.user_data_dir:
            self.temp_dir = tempfile.mkdtemp(prefix="browser-profile-")
            self.user_data_dir = self.temp_dir

        # Get browser path and args based on OS and browser type
        # browser_path = self._get_browser_path()
        args = await self._get_browser_args()
        
        if self.browser_config.extra_args:
            args.extend(self.browser_config.extra_args)
            

        # ── make sure no old Chromium instance is owning the same port/profile ──
        try:
            if sys.platform == "win32":
                if psutil is None:
                    raise RuntimeError("psutil not available, cannot clean old browser")
                for p in psutil.process_iter(["pid", "name", "cmdline"]):
                    cl = " ".join(p.info.get("cmdline") or [])
                    if (
                        f"--remote-debugging-port={self.debugging_port}" in cl
                        and f"--user-data-dir={self.user_data_dir}" in cl
                    ):
                        p.kill()
                        p.wait(timeout=5)
            else:  # macOS / Linux
                # kill any process listening on the same debugging port
                try:
                    pids = (
                        subprocess.check_output(
                            shlex.split(f"lsof -t -i:{self.debugging_port}"),
                            stderr=subprocess.DEVNULL,
                        )
                        .decode()
                        .strip()
                        .splitlines()
                    )
                except (FileNotFoundError, subprocess.CalledProcessError):
                    pids = []
                for pid in pids:
                    try:
                        os.kill(int(pid), signal.SIGTERM)
                    except ProcessLookupError:
                        pass

                # remove Chromium singleton locks, or new launch exits with
                # “Opening in existing browser session.”
                for f in ("SingletonLock", "SingletonSocket", "SingletonCookie"):
                    fp = os.path.join(self.user_data_dir, f)
                    if os.path.exists(fp):
                        os.remove(fp)
        except Exception as _e:
            # non-fatal — we'll try to start anyway, but log what happened
            self.logger.warning(f"pre-launch cleanup failed: {_e}", tag="BROWSER")            
            

        # Start browser process
        try:
            # Use DETACHED_PROCESS flag on Windows to fully detach the process
            # On Unix, we'll use preexec_fn=os.setpgrp to start the process in a new process group
            if sys.platform == "win32":
                self.browser_process = subprocess.Popen(
                    args, 
                    stdout=subprocess.PIPE, 
                    stderr=subprocess.PIPE,
                    creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
                )
            else:
                self.browser_process = subprocess.Popen(
                    args, 
                    stdout=subprocess.PIPE, 
                    stderr=subprocess.PIPE,
                    preexec_fn=os.setpgrp  # Start in a new process group
                )
                
            # If verbose is True print args used to run the process
            if self.logger and self.browser_config.verbose:
                self.logger.debug(
                    f"Starting browser with args: {' '.join(args)}",
                    tag="BROWSER"
                )    
                
            # We'll monitor for a short time to make sure it starts properly, but won't keep monitoring
            await asyncio.sleep(0.5)  # Give browser time to start
            await self._initial_startup_check()
            await asyncio.sleep(2)  # Give browser time to start
            return f"http://{self.host}:{self.debugging_port}"
        except Exception as e:
            await self.cleanup()
            raise Exception(f"Failed to start browser: {e}")

    async def _initial_startup_check(self):
        """
        Perform a quick check to make sure the browser started successfully.
        This only runs once at startup rather than continuously monitoring.
        """
        if not self.browser_process:
            return
            
        # Check that process started without immediate termination
        await asyncio.sleep(0.5)
        if self.browser_process.poll() is not None:
            # Process already terminated
            stdout, stderr = b"", b""
            try:
                stdout, stderr = self.browser_process.communicate(timeout=0.5)
            except subprocess.TimeoutExpired:
                pass
                
            self.logger.error(
                message="Browser process terminated during startup | Code: {code} | STDOUT: {stdout} | STDERR: {stderr}",
                tag="ERROR",
                params={
                    "code": self.browser_process.returncode,
                    "stdout": stdout.decode() if stdout else "",
                    "stderr": stderr.decode() if stderr else "",
                },
            )
    
    async def _monitor_browser_process(self):
        """
        Monitor the browser process for unexpected termination.

        How it works:
        1. Read stdout and stderr from the browser process.
        2. If the process has terminated, log the error message and terminate the browser.
        3. If the shutting_down flag is set, log the normal termination message.
        4. If any other error occurs, log the error message.

        Note: This method should be called in a separate task to avoid blocking the main event loop.
        This is DEPRECATED and should not be used for builtin browsers that need to outlive the Python process.
        """
        if self.browser_process:
            try:
                stdout, stderr = await asyncio.gather(
                    asyncio.to_thread(self.browser_process.stdout.read),
                    asyncio.to_thread(self.browser_process.stderr.read),
                )

                # Check shutting_down flag BEFORE logging anything
                if self.browser_process.poll() is not None:
                    if not self.shutting_down:
                        self.logger.error(
                            message="Browser process terminated unexpectedly | Code: {code} | STDOUT: {stdout} | STDERR: {stderr}",
                            tag="ERROR",
                            params={
                                "code": self.browser_process.returncode,
                                "stdout": stdout.decode(),
                                "stderr": stderr.decode(),
                            },
                        )
                        await self.cleanup()
                    else:
                        self.logger.info(
                            message="Browser process terminated normally | Code: {code}",
                            tag="INFO",
                            params={"code": self.browser_process.returncode},
                        )
            except Exception as e:
                if not self.shutting_down:
                    self.logger.error(
                        message="Error monitoring browser process: {error}",
                        tag="ERROR",
                        params={"error": str(e)},
                    )

    def _get_browser_path_WIP(self) -> str:
        """Returns the browser executable path based on OS and browser type"""
        if sys.platform == "darwin":  # macOS
            paths = {
                "chromium": "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                "firefox": "/Applications/Firefox.app/Contents/MacOS/firefox",
                "webkit": "/Applications/Safari.app/Contents/MacOS/Safari",
            }
        elif sys.platform == "win32":  # Windows
            paths = {
                "chromium": "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
                "firefox": "C:\\Program Files\\Mozilla Firefox\\firefox.exe",
                "webkit": None,  # WebKit not supported on Windows
            }
        else:  # Linux
            paths = {
                "chromium": "google-chrome",
                "firefox": "firefox",
                "webkit": None,  # WebKit not supported on Linux
            }

        return paths.get(self.browser_type)

    async def _get_browser_path(self) -> str:
        browser_path = await get_chromium_path(self.browser_type)
        return browser_path

    async def _get_browser_args(self) -> List[str]:
        """Returns full CLI args for launching the browser"""
        base = [await self._get_browser_path()]
        if self.browser_type == "chromium":
            flags = [
                f"--remote-debugging-port={self.debugging_port}",
                f"--user-data-dir={self.user_data_dir}",
            ]
            if self.headless:
                flags.append("--headless=new")
            # Add viewport flag if specified in config
            if self.browser_config.viewport_height and self.browser_config.viewport_width:
                flags.append(f"--window-size={self.browser_config.viewport_width},{self.browser_config.viewport_height}")
            # merge common launch flags
            flags.extend(self.build_browser_flags(self.browser_config))
        elif self.browser_type == "firefox":
            flags = [
                "--remote-debugging-port",
                str(self.debugging_port),
                "--profile",
                self.user_data_dir,
            ]
            if self.headless:
                flags.append("--headless")
        else:
            raise NotImplementedError(f"Browser type {self.browser_type} not supported")
        return base + flags

    async def cleanup(self):
        """Cleanup browser process and temporary directory"""
        # Set shutting_down flag BEFORE any termination actions
        self.shutting_down = True

        if self.browser_process:
            try:
                # For builtin browsers that should persist, we should check if it's a detached process
                # Only terminate if we have proper control over the process
                if not self.browser_process.poll():
                    # Process is still running
                    self.browser_process.terminate()
                    # Wait for process to end gracefully
                    for _ in range(10):  # 10 attempts, 100ms each
                        if self.browser_process.poll() is not None:
                            break
                        await asyncio.sleep(0.1)

                    # Force kill if still running
                    if self.browser_process.poll() is None:
                        if sys.platform == "win32":
                            # On Windows, use taskkill /T to kill the entire process tree
                            try:
                                subprocess.run(["taskkill", "/F", "/T", "/PID", str(self.browser_process.pid)])
                            except Exception:
                                self.browser_process.kill()
                        else:
                            # On Unix, kill entire process group to reap child processes
                            try:
                                os.killpg(os.getpgid(self.browser_process.pid), signal.SIGKILL)
                            except (ProcessLookupError, OSError):
                                pass
                        await asyncio.sleep(0.1)  # Brief wait for kill to take effect

            except Exception as e:
                self.logger.error(
                    message="Error terminating browser: {error}",
                    tag="ERROR", 
                    params={"error": str(e)},
                )

        if self.temp_dir and os.path.exists(self.temp_dir):
            try:
                shutil.rmtree(self.temp_dir)
            except Exception as e:
                self.logger.error(
                    message="Error removing temporary directory: {error}",
                    tag="ERROR",
                    params={"error": str(e)},
                )
                
    # These methods have been moved to BrowserProfiler class
    @staticmethod
    async def create_profile(browser_config=None, profile_name=None, logger=None):
        """
        This method has been moved to the BrowserProfiler class.
        
        Creates a browser profile by launching a browser for interactive user setup
        and waits until the user closes it. The profile is stored in a directory that
        can be used later with BrowserConfig.user_data_dir.
        
        Please use BrowserProfiler.create_profile() instead.
        
        Example:
            ```python
            from crawl4ai.browser_profiler import BrowserProfiler
            
            profiler = BrowserProfiler()
            profile_path = await profiler.create_profile(profile_name="my-login-profile")
            ```
        """
        from .browser_profiler import BrowserProfiler
        
        # Create a BrowserProfiler instance and delegate to it
        profiler = BrowserProfiler(logger=logger)
        return await profiler.create_profile(profile_name=profile_name, browser_config=browser_config)
    
    @staticmethod
    def list_profiles():
        """
        This method has been moved to the BrowserProfiler class.
        
        Lists all available browser profiles in the Crawl4AI profiles directory.
        
        Please use BrowserProfiler.list_profiles() instead.
        
        Example:
            ```python
            from crawl4ai.browser_profiler import BrowserProfiler
            
            profiler = BrowserProfiler()
            profiles = profiler.list_profiles()
            ```
        """
        from .browser_profiler import BrowserProfiler
        
        # Create a BrowserProfiler instance and delegate to it
        profiler = BrowserProfiler()
        return profiler.list_profiles()
        
    @staticmethod
    def delete_profile(profile_name_or_path):
        """
        This method has been moved to the BrowserProfiler class.
        
        Delete a browser profile by name or path.
        
        Please use BrowserProfiler.delete_profile() instead.
        
        Example:
            ```python
            from crawl4ai.browser_profiler import BrowserProfiler
            
            profiler = BrowserProfiler()
            success = profiler.delete_profile("my-profile")
            ```
        """
        from .browser_profiler import BrowserProfiler
        
        # Create a BrowserProfiler instance and delegate to it
        profiler = BrowserProfiler()
        return profiler.delete_profile(profile_name_or_path)


async def clone_runtime_state(
    src: BrowserContext,
    dst: BrowserContext,
    crawlerRunConfig: CrawlerRunConfig | None = None,
    browserConfig: BrowserConfig | None = None,
) -> None:
    """
    Bring everything that *can* be changed at runtime from `src` → `dst`.

    1. Cookies
    2. localStorage (and sessionStorage, same API)
    3. Extra headers, permissions, geolocation if supplied in configs
    """

    # ── 1. cookies ────────────────────────────────────────────────────────────
    cookies = await src.cookies()
    if cookies:
        await dst.add_cookies(cookies)

    # ── 2. localStorage / sessionStorage ──────────────────────────────────────
    state = await src.storage_state()
    for origin in state.get("origins", []):
        url = origin["origin"]
        kvs = origin.get("localStorage", [])
        if not kvs:
            continue

        page = dst.pages[0] if dst.pages else await dst.new_page()
        await page.goto(url, wait_until="domcontentloaded")
        for k, v in kvs:
            await page.evaluate("(k,v)=>localStorage.setItem(k,v)", k, v)

    # ── 3. runtime-mutable extras from configs ────────────────────────────────
    # headers
    if browserConfig and browserConfig.headers:
        await dst.set_extra_http_headers(browserConfig.headers)

    # geolocation
    if crawlerRunConfig and crawlerRunConfig.geolocation:
        await dst.grant_permissions(["geolocation"])
        await dst.set_geolocation(
            {
                "latitude": crawlerRunConfig.geolocation.latitude,
                "longitude": crawlerRunConfig.geolocation.longitude,
                "accuracy": crawlerRunConfig.geolocation.accuracy,
            }
        )
        
    return dst



class _CDPConnectionCache:
    """
    Class-level cache for Playwright + CDP browser connections.

    When enabled via BrowserConfig(cache_cdp_connection=True), multiple
    BrowserManager instances connecting to the same cdp_url will share
    a single Playwright subprocess and CDP WebSocket. Reference-counted;
    the connection is closed when the last user releases it.
    """

    _cache: Dict[str, Tuple] = {}  # cdp_url -> (playwright, browser, ref_count)
    _lock: Optional[asyncio.Lock] = None  # lazy-init to avoid event loop issues
    _lock_loop: Optional[asyncio.AbstractEventLoop] = None

    @classmethod
    def _get_lock(cls) -> asyncio.Lock:
        loop = asyncio.get_running_loop()
        if cls._lock is None or cls._lock_loop is not loop:
            cls._lock = asyncio.Lock()
            cls._lock_loop = loop
        return cls._lock

    @classmethod
    async def acquire(cls, cdp_url: str, use_undetected: bool = False):
        """Get or create a cached (playwright, browser) for this cdp_url."""
        async with cls._get_lock():
            if cdp_url in cls._cache:
                pw, browser, count = cls._cache[cdp_url]
                if browser.is_connected():
                    cls._cache[cdp_url] = (pw, browser, count + 1)
                    return pw, browser
                # Stale connection — clean up and fall through to create new
                try:
                    await pw.stop()
                except Exception:
                    pass
                del cls._cache[cdp_url]

            # Create new connection
            if use_undetected:
                from patchright.async_api import async_playwright
            else:
                from playwright.async_api import async_playwright
            pw = await async_playwright().start()
            browser = await pw.chromium.connect_over_cdp(cdp_url)
            cls._cache[cdp_url] = (pw, browser, 1)
            return pw, browser

    @classmethod
    async def release(cls, cdp_url: str):
        """Decrement ref count; close connection when last user releases."""
        async with cls._get_lock():
            if cdp_url not in cls._cache:
                return
            pw, browser, count = cls._cache[cdp_url]
            if count <= 1:
                try:
                    await browser.close()
                except Exception:
                    pass
                try:
                    await pw.stop()
                except Exception:
                    pass
                del cls._cache[cdp_url]
            else:
                cls._cache[cdp_url] = (pw, browser, count - 1)

    @classmethod
    async def close_all(cls):
        """Force-close all cached connections. Call on application shutdown."""
        async with cls._get_lock():
            for cdp_url in list(cls._cache.keys()):
                pw, browser, _ = cls._cache[cdp_url]
                try:
                    await browser.close()
                except Exception:
                    pass
                try:
                    await pw.stop()
                except Exception:
                    pass
            cls._cache.clear()


class BrowserManager:
    """
    Manages the browser instance and context.

    Attributes:
        config (BrowserConfig): Configuration object containing all browser settings
        logger: Logger instance for recording events and errors
        browser (Browser): The browser instance
        default_context (BrowserContext): The default browser context
        managed_browser (ManagedBrowser): The managed browser instance
        playwright (Playwright): The Playwright instance
        sessions (dict): Dictionary to store session information
        session_ttl (int): Session timeout in seconds
    """

    _playwright_instance = None

    # Class-level tracking of pages in use, keyed by browser endpoint (CDP URL or instance id)
    # This ensures multiple BrowserManager instances connecting to the same browser
    # share the same page tracking, preventing race conditions.
    _global_pages_in_use: dict = {}  # endpoint_key -> set of pages
    _global_pages_lock: asyncio.Lock = None  # Initialized lazily

    @classmethod
    def _get_global_lock(cls) -> asyncio.Lock:
        """Get or create the global pages lock (lazy initialization for async context)."""
        if cls._global_pages_lock is None:
            cls._global_pages_lock = asyncio.Lock()
        return cls._global_pages_lock

    @classmethod
    async def get_playwright(cls, use_undetected: bool = False):
        if use_undetected:
            from patchright.async_api import async_playwright
        else:
            from playwright.async_api import async_playwright
        cls._playwright_instance = await async_playwright().start()
        return cls._playwright_instance    

    def __init__(self, browser_config: BrowserConfig, logger=None, use_undetected: bool = False):
        """
        Initialize the BrowserManager with a browser configuration.

        Args:
            browser_config (BrowserConfig): Configuration object containing all browser settings
            logger: Logger instance for recording events and errors
            use_undetected (bool): Whether to use undetected browser (Patchright)
        """
        self.config: BrowserConfig = browser_config
        self.logger = logger
        self.use_undetected = use_undetected

        # Browser state
        self.browser = None
        self.default_context = None
        self.managed_browser = None
        self.playwright = None
        self._using_cached_cdp = False
        self._launched_persistent = False  # True when using launch_persistent_context

        # Session management
        self.sessions = {}
        self.session_ttl = 1800  # 30 minutes

        # Keep track of contexts by a "config signature," so each unique config reuses a single context
        self.contexts_by_config = {}
        self._contexts_lock = asyncio.Lock()

        # Context lifecycle tracking for LRU eviction
        self._context_refcounts = {}    # sig -> int  (active crawls using this context)
        self._context_last_used = {}    # sig -> float (monotonic timestamp for LRU)
        self._page_to_sig = {}          # page -> sig  (for decrement lookup on release)
        self._max_contexts = 20         # LRU eviction threshold

        # Serialize context.new_page() across concurrent tasks to avoid races
        # when using a shared persistent context (context.pages may be empty
        # for all racers). Prevents 'Target page/context closed' errors.
        self._page_lock = asyncio.Lock()

        # Browser endpoint key for global page tracking (set after browser starts)
        self._browser_endpoint_key: Optional[str] = None

        # Browser recycling state (version-based approach)
        self._pages_served = 0
        self._browser_version = 1  # included in signature, bump to create new browser
        self._pending_cleanup = {}  # old_sig -> {"browser": browser, "contexts": [...], "done": Event}
        self._pending_cleanup_lock = asyncio.Lock()
        self._max_pending_browsers = 3  # safety cap — block if too many draining
        self._cleanup_slot_available = asyncio.Event()
        self._cleanup_slot_available.set()  # starts open

        # Stealth adapter for stealth mode
        self._stealth_adapter = None
        if self.config.enable_stealth and not self.use_undetected:
            from .browser_adapter import StealthAdapter
            self._stealth_adapter = StealthAdapter()

        # Initialize ManagedBrowser if needed
        if self.config.use_managed_browser:
            self.managed_browser = ManagedBrowser(
                browser_type=self.config.browser_type,
                user_data_dir=self.config.user_data_dir,
                headless=self.config.headless,
                logger=self.logger,
                debugging_port=self.config.debugging_port,
                cdp_url=self.config.cdp_url,
                browser_config=self.config,
            )

    async def start(self):
        """
        Start the browser instance and set up the default context.

        How it works:
        1. Check if Playwright is already initialized.
        2. If not, initialize Playwright.
        3. If managed browser is used, start it and connect to the CDP endpoint.
        4. If managed browser is not used, launch the browser and set up the default context.

        Note: This method should be called in a separate task to avoid blocking the main event loop.
        """
        if self.playwright is not None:
            await self.close()

        # Use cached CDP connection if enabled and cdp_url is set
        if self.config.cache_cdp_connection and self.config.cdp_url:
            self._using_cached_cdp = True
            self.config.use_managed_browser = True
            self.playwright, self.browser = await _CDPConnectionCache.acquire(
                self.config.cdp_url, self.use_undetected
            )
        else:
            self._using_cached_cdp = False
            if self.use_undetected:
                from patchright.async_api import async_playwright
            else:
                from playwright.async_api import async_playwright

            # Initialize playwright
            self.playwright = await async_playwright().start()

        # ── Persistent context via Playwright's native API ──────────────
        # When use_persistent_context is set and we're not connecting to an
        # external CDP endpoint, use launch_persistent_context() instead of
        # subprocess + CDP.  This properly supports proxy authentication
        # (server + username + password) which the --proxy-server CLI flag
        # cannot handle.
        if (
            self.config.use_persistent_context
            and not self.config.cdp_url
            and not self._using_cached_cdp
        ):
            # Collect stealth / optimization CLI flags, excluding ones that
            # launch_persistent_context handles via keyword arguments.
            _skip_prefixes = (
                "--proxy-server",
                "--remote-debugging-port",
                "--user-data-dir",
                "--headless",
                "--window-size",
            )
            cli_args = [
                flag
                for flag in ManagedBrowser.build_browser_flags(self.config)
                if not flag.startswith(_skip_prefixes)
            ]
            if self.config.extra_args:
                cli_args.extend(self.config.extra_args)

            launch_kwargs = {
                "headless": self.config.headless,
                "args": list(dict.fromkeys(cli_args)),  # dedupe
                "viewport": {
                    "width": self.config.viewport_width,
                    "height": self.config.viewport_height,
                },
                "user_agent": self.config.user_agent or None,
                "ignore_https_errors": self.config.ignore_https_errors,
                "accept_downloads": self.config.accept_downloads,
            }

            if self.config.proxy_config:
                launch_kwargs["proxy"] = {
                    "server": self.config.proxy_config.server,
                    "username": self.config.proxy_config.username,
                    "password": self.config.proxy_config.password,
                }

            if self.config.storage_state:
                launch_kwargs["storage_state"] = self.config.storage_state

            user_data_dir = self.config.user_data_dir or tempfile.mkdtemp(
                prefix="crawl4ai-persistent-"
            )

            self.default_context = (
                await self.playwright.chromium.launch_persistent_context(
                    user_data_dir, **launch_kwargs
                )
            )
            self.browser = None  # persistent context has no separate Browser
            self._launched_persistent = True

            await self.setup_context(self.default_context)

            # Set the browser endpoint key for global page tracking
            self._browser_endpoint_key = self._compute_browser_endpoint_key()
            if self._browser_endpoint_key not in BrowserManager._global_pages_in_use:
                BrowserManager._global_pages_in_use[self._browser_endpoint_key] = set()
            return

        if self.config.cdp_url or self.config.use_managed_browser:
            self.config.use_managed_browser = True

            if not self._using_cached_cdp:
                cdp_url = await self.managed_browser.start() if not self.config.cdp_url else self.config.cdp_url

                # Add CDP endpoint verification before connecting
                if not await self._verify_cdp_ready(cdp_url):
                    raise Exception(f"CDP endpoint at {cdp_url} is not ready after startup")

                self.browser = await self.playwright.chromium.connect_over_cdp(cdp_url)

            contexts = self.browser.contexts

            # If browser_context_id is provided, we're using a pre-created context
            if self.config.browser_context_id:
                if self.logger:
                    self.logger.debug(
                        f"Using pre-existing browser context: {self.config.browser_context_id}",
                        tag="BROWSER"
                    )
                # When connecting to a pre-created context, it should be in contexts
                if contexts:
                    self.default_context = contexts[0]
                    if self.logger:
                        self.logger.debug(
                            f"Found {len(contexts)} existing context(s), using first one",
                            tag="BROWSER"
                        )
                else:
                    # Context was created but not yet visible - wait a bit
                    await asyncio.sleep(0.2)
                    contexts = self.browser.contexts
                    if contexts:
                        self.default_context = contexts[0]
                    else:
                        # Still no contexts - this shouldn't happen with pre-created context
                        if self.logger:
                            self.logger.warning(
                                "Pre-created context not found, creating new one",
                                tag="BROWSER"
                            )
                        self.default_context = await self.create_browser_context()
            elif contexts:
                self.default_context = contexts[0]
            else:
                self.default_context = await self.create_browser_context()
            await self.setup_context(self.default_context)
        else:
            browser_args = self._build_browser_args()

            # Launch appropriate browser type
            if self.config.browser_type == "firefox":
                self.browser = await self.playwright.firefox.launch(**browser_args)
            elif self.config.browser_type == "webkit":
                self.browser = await self.playwright.webkit.launch(**browser_args)
            else:
                self.browser = await self.playwright.chromium.launch(**browser_args)

            self.default_context = self.browser

        # Set the browser endpoint key for global page tracking
        self._browser_endpoint_key = self._compute_browser_endpoint_key()
        # Initialize global tracking set for this endpoint if needed
        if self._browser_endpoint_key not in BrowserManager._global_pages_in_use:
            BrowserManager._global_pages_in_use[self._browser_endpoint_key] = set()

    def _compute_browser_endpoint_key(self) -> str:
        """
        Compute a unique key identifying this browser connection.

        For CDP connections, uses the normalized CDP URL so all BrowserManager
        instances connecting to the same browser share page tracking.
        For standalone browsers, uses instance id since each is independent.

        Returns:
            str: Unique identifier for this browser connection
        """
        # For CDP connections, use the CDP URL as the key (normalized)
        if self.config.cdp_url:
            return self._normalize_cdp_url(self.config.cdp_url)

        # For managed browsers, use the CDP URL/port that was assigned
        if self.managed_browser:
            # Use debugging port as the key since it uniquely identifies the browser
            port = getattr(self.managed_browser, 'debugging_port', None)
            host = getattr(self.managed_browser, 'host', 'localhost')
            if port:
                return f"cdp:http://{host}:{port}"

        # For standalone browsers, use instance id (no sharing needed)
        return f"instance:{id(self)}"

    def _normalize_cdp_url(self, cdp_url: str) -> str:
        """
        Normalize a CDP URL to a canonical form for consistent tracking.

        Handles various formats:
        - http://localhost:9222
        - ws://localhost:9222/devtools/browser/xxx
        - http://localhost:9222?browser_id=xxx

        Returns:
            str: Normalized CDP key in format "cdp:http://host:port"
        """
        from urllib.parse import urlparse

        parsed = urlparse(cdp_url)
        host = parsed.hostname or 'localhost'
        port = parsed.port or 9222

        return f"cdp:http://{host}:{port}"

    def _get_pages_in_use(self) -> set:
        """Get the set of pages currently in use for this browser."""
        if self._browser_endpoint_key and self._browser_endpoint_key in BrowserManager._global_pages_in_use:
            return BrowserManager._global_pages_in_use[self._browser_endpoint_key]
        # Fallback: shouldn't happen, but return empty set
        return set()

    def _mark_page_in_use(self, page) -> None:
        """Mark a page as in use."""
        if self._browser_endpoint_key:
            if self._browser_endpoint_key not in BrowserManager._global_pages_in_use:
                BrowserManager._global_pages_in_use[self._browser_endpoint_key] = set()
            BrowserManager._global_pages_in_use[self._browser_endpoint_key].add(page)

    def _release_page_from_use(self, page) -> None:
        """Release a page from the in-use tracking."""
        if self._browser_endpoint_key and self._browser_endpoint_key in BrowserManager._global_pages_in_use:
            BrowserManager._global_pages_in_use[self._browser_endpoint_key].discard(page)

    async def _verify_cdp_ready(self, cdp_url: str) -> bool:
        """Verify CDP endpoint is ready with exponential backoff.

        Supports multiple URL formats:
        - HTTP URLs: http://localhost:9222
        - HTTP URLs with query params: http://localhost:9222?browser_id=XXX
        - WebSocket URLs: ws://localhost:9222/devtools/browser/XXX
        """
        import aiohttp
        from urllib.parse import urlparse, urlunparse

        # If WebSocket URL, Playwright handles connection directly - skip HTTP verification
        if cdp_url.startswith(('ws://', 'wss://')):
            self.logger.debug(f"WebSocket CDP URL provided, skipping HTTP verification", tag="BROWSER")
            return True

        # Parse HTTP URL and properly construct /json/version endpoint
        parsed = urlparse(cdp_url)
        # Build URL with /json/version path, preserving query params
        verify_url = urlunparse((
            parsed.scheme,
            parsed.netloc,
            '/json/version',  # Always use this path for verification
            '',  # params
            parsed.query,  # preserve query string
            ''   # fragment
        ))

        self.logger.debug(f"Starting CDP verification for {verify_url}", tag="BROWSER")
        for attempt in range(5):
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(verify_url, timeout=aiohttp.ClientTimeout(total=2)) as response:
                        if response.status == 200:
                            self.logger.debug(f"CDP endpoint ready after {attempt + 1} attempts", tag="BROWSER")
                            return True
            except Exception as e:
                self.logger.debug(f"CDP check attempt {attempt + 1} failed: {e}", tag="BROWSER")
            delay = 0.5 * (1.4 ** attempt)
            self.logger.debug(f"Waiting {delay:.2f}s before next CDP check...", tag="BROWSER")
            await asyncio.sleep(delay)
        self.logger.debug(f"CDP verification failed after 5 attempts", tag="BROWSER")
        return False

    def _build_browser_args(self) -> dict:
        """Build browser launch arguments from config."""
        args = [
            "--disable-gpu",
            "--disable-gpu-compositing",
            "--disable-software-rasterizer",
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-infobars",
            "--window-position=0,0",
            "--ignore-certificate-errors",
            "--ignore-certificate-errors-spki-list",
            "--disable-blink-features=AutomationControlled",
            "--window-position=400,0",
            "--disable-renderer-backgrounding",
            "--disable-ipc-flooding-protection",
            "--force-color-profile=srgb",
            "--mute-audio",
            "--disable-background-timer-throttling",
            # Memory-saving flags: disable unused Chrome features
            "--disable-features=OptimizationHints,MediaRouter,DialMediaRouteProvider",
            "--disable-component-update",
            "--disable-domain-reliability",
            # "--single-process",
            f"--window-size={self.config.viewport_width},{self.config.viewport_height}",
        ]

        if self.config.memory_saving_mode:
            args.extend([
                "--aggressive-cache-discard",
                '--js-flags=--max-old-space-size=512',
            ])

        if self.config.light_mode:
            args.extend(BROWSER_DISABLE_OPTIONS)

        if self.config.text_mode:
            args.extend(
                [
                    "--blink-settings=imagesEnabled=false",
                    "--disable-remote-fonts",
                    "--disable-images",
                    "--disable-javascript",
                    "--disable-software-rasterizer",
                    "--disable-dev-shm-usage",
                ]
            )

        if self.config.extra_args:
            args.extend(self.config.extra_args)

        # Deduplicate args
        args = list(dict.fromkeys(args))
        
        browser_args = {"headless": self.config.headless, "args": args}

        if self.config.chrome_channel:
            browser_args["channel"] = self.config.chrome_channel

        if self.config.accept_downloads:
            browser_args["downloads_path"] = self.config.downloads_path or os.path.join(
                os.getcwd(), "downloads"
            )
            os.makedirs(browser_args["downloads_path"], exist_ok=True)

        if self.config.proxy:
            warnings.warn(
                "BrowserConfig.proxy is deprecated and ignored. Use proxy_config instead.",
                DeprecationWarning,
            )
        if self.config.proxy_config:
            from playwright.async_api import ProxySettings

            proxy_settings = ProxySettings(
                server=self.config.proxy_config.server,
                username=self.config.proxy_config.username,
                password=self.config.proxy_config.password,
            )
            browser_args["proxy"] = proxy_settings

        return browser_args

    async def setup_context(
        self,
        context: BrowserContext,
        crawlerRunConfig: CrawlerRunConfig = None,
        is_default=False,
    ):
        """
        Set up a browser context with the configured options.

        How it works:
        1. Set extra HTTP headers if provided.
        2. Add cookies if provided.
        3. Load storage state if provided.
        4. Accept downloads if enabled.
        5. Set default timeouts for navigation and download.
        6. Set user agent if provided.
        7. Set browser hints if provided.
        8. Set proxy if provided.
        9. Set downloads path if provided.
        10. Set storage state if provided.
        11. Set cache if provided.
        12. Set extra HTTP headers if provided.
        13. Add cookies if provided.
        14. Set default timeouts for navigation and download if enabled.
        15. Set user agent if provided.
        16. Set browser hints if provided.

        Args:
            context (BrowserContext): The browser context to set up
            crawlerRunConfig (CrawlerRunConfig): Configuration object containing all browser settings
            is_default (bool): Flag indicating if this is the default context
        Returns:
            None
        """
        if self.config.headers:
            await context.set_extra_http_headers(self.config.headers)

        if self.config.cookies:
            await context.add_cookies(self.config.cookies)

        if self.config.storage_state:
            await context.storage_state(path=None)

        if self.config.accept_downloads:
            context.set_default_timeout(DOWNLOAD_PAGE_TIMEOUT)
            context.set_default_navigation_timeout(DOWNLOAD_PAGE_TIMEOUT)
            if self.config.downloads_path:
                context._impl_obj._options["accept_downloads"] = True
                context._impl_obj._options[
                    "downloads_path"
                ] = self.config.downloads_path

        # Handle user agent and browser hints
        if self.config.user_agent:
            combined_headers = {
                "User-Agent": self.config.user_agent,
                "sec-ch-ua": self.config.browser_hint,
            }
            combined_headers.update(self.config.headers)
            await context.set_extra_http_headers(combined_headers)

        # Add default cookie (skip for raw:/file:// URLs which are not valid cookie URLs)
        cookie_url = None
        if crawlerRunConfig and crawlerRunConfig.url:
            url = crawlerRunConfig.url
            # Only set cookie for http/https URLs
            if url.startswith(("http://", "https://")):
                cookie_url = url
            elif crawlerRunConfig.base_url and crawlerRunConfig.base_url.startswith(("http://", "https://")):
                # Use base_url as fallback for raw:/file:// URLs
                cookie_url = crawlerRunConfig.base_url

        if cookie_url:
            await context.add_cookies(
                [
                    {
                        "name": "cookiesEnabled",
                        "value": "true",
                        "url": cookie_url,
                    }
                ]
            )

        # Handle navigator overrides
        if crawlerRunConfig:
            if (
                crawlerRunConfig.override_navigator
                or crawlerRunConfig.simulate_user
                or crawlerRunConfig.magic
            ):
                await context.add_init_script(load_js_script("navigator_overrider"))
                context._crawl4ai_nav_overrider_injected = True

        # Force-open closed shadow roots when flatten_shadow_dom is enabled
        if crawlerRunConfig and crawlerRunConfig.flatten_shadow_dom:
            await context.add_init_script("""
                const _origAttachShadow = Element.prototype.attachShadow;
                Element.prototype.attachShadow = function(init) {
                    return _origAttachShadow.call(this, {...init, mode: 'open'});
                };
            """)
            context._crawl4ai_shadow_dom_injected = True

        # Apply custom init_scripts from BrowserConfig (for stealth evasions, etc.)
        if self.config.init_scripts:
            for script in self.config.init_scripts:
                await context.add_init_script(script)

    async def create_browser_context(self, crawlerRunConfig: CrawlerRunConfig = None):
        """
        Creates and returns a new browser context with configured settings.
        Applies text-only mode settings if text_mode is enabled in config.

        Returns:
            Context: Browser context object with the specified configurations
        """
        if self.browser is None:
            if self._launched_persistent:
                raise RuntimeError(
                    "Cannot create new browser contexts when using "
                    "use_persistent_context=True. Persistent context uses a "
                    "single shared context."
                )
            raise RuntimeError(
                "Browser is not available. It may have been closed, crashed, "
                "or not yet started. Ensure the browser is running before "
                "creating new contexts."
            )
        # Base settings
        user_agent = self.config.headers.get("User-Agent", self.config.user_agent) 
        viewport_settings = {
            "width": self.config.viewport_width,
            "height": self.config.viewport_height,
        }
        proxy_settings = {"server": self.config.proxy} if self.config.proxy else None

        # CSS extensions (blocked separately via avoid_css flag)
        css_extensions = ["css", "less", "scss", "sass"]

        # Static resource extensions (blocked when text_mode is enabled)
        static_extensions = [
            # Images
            "jpg", "jpeg", "png", "gif", "webp", "svg", "ico", "bmp", "tiff", "psd",
            # Fonts
            "woff", "woff2", "ttf", "otf", "eot",
            # Media
            "mp4", "webm", "ogg", "avi", "mov", "wmv", "flv", "m4v",
            "mp3", "wav", "aac", "m4a", "opus", "flac",
            # Documents
            "pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx",
            # Archives
            "zip", "rar", "7z", "tar", "gz",
            # Scripts and data
            "xml", "swf", "wasm",
        ]

        # Ad and tracker domain patterns (curated from uBlock/EasyList sources)
        ad_tracker_patterns = [
            "**/google-analytics.com/**",
            "**/googletagmanager.com/**",
            "**/googlesyndication.com/**",
            "**/doubleclick.net/**",
            "**/adservice.google.com/**",
            "**/adsystem.com/**",
            "**/adzerk.net/**",
            "**/adnxs.com/**",
            "**/ads.linkedin.com/**",
            "**/facebook.net/**",
            "**/analytics.twitter.com/**",
            "**/ads-twitter.com/**",
            "**/hotjar.com/**",
            "**/clarity.ms/**",
            "**/scorecardresearch.com/**",
            "**/pixel.wp.com/**",
            "**/amazon-adsystem.com/**",
            "**/mixpanel.com/**",
            "**/segment.com/**",
        ]

        # Common context settings
        context_settings = {
            "user_agent": user_agent,
            "viewport": viewport_settings,
            "proxy": proxy_settings,
            "accept_downloads": self.config.accept_downloads,
            "storage_state": self.config.storage_state,
            "ignore_https_errors": self.config.ignore_https_errors,
            "device_scale_factor": self.config.device_scale_factor,
            "java_script_enabled": self.config.java_script_enabled,
        }
        
        if crawlerRunConfig:
            # Check if there is value for crawlerRunConfig.proxy_config set add that to context
            if crawlerRunConfig.proxy_config:
                from playwright.async_api import ProxySettings
                proxy_settings = ProxySettings(
                    server=crawlerRunConfig.proxy_config.server,
                    username=crawlerRunConfig.proxy_config.username,
                    password=crawlerRunConfig.proxy_config.password,
                )
                context_settings["proxy"] = proxy_settings

        if self.config.text_mode:
            text_mode_settings = {
                "has_touch": False,
                "is_mobile": False,
            }
            # Update context settings with text mode settings
            context_settings.update(text_mode_settings)

        # inject locale / tz / geo if user provided them
        if crawlerRunConfig:
            if crawlerRunConfig.locale:
                context_settings["locale"] = crawlerRunConfig.locale
            if crawlerRunConfig.timezone_id:
                context_settings["timezone_id"] = crawlerRunConfig.timezone_id
            if crawlerRunConfig.geolocation:
                context_settings["geolocation"] = {
                    "latitude": crawlerRunConfig.geolocation.latitude,
                    "longitude": crawlerRunConfig.geolocation.longitude,
                    "accuracy": crawlerRunConfig.geolocation.accuracy,
                }
                # ensure geolocation permission
                perms = context_settings.get("permissions", [])
                perms.append("geolocation")
                context_settings["permissions"] = perms

        # Create and return the context with all settings
        context = await self.browser.new_context(**context_settings)

        # Build dynamic blocking list based on config flags
        to_block = []
        if self.config.avoid_css:
            to_block.extend(css_extensions)
        if self.config.text_mode:
            to_block.extend(static_extensions)

        if to_block:
            for ext in to_block:
                await context.route(f"**/*.{ext}", lambda route: route.abort())

        if self.config.avoid_ads:
            for pattern in ad_tracker_patterns:
                await context.route(pattern, lambda route: route.abort())

        # TODO: Strip infrastructure-injected headers that leak datacenter origin
        # (e.g. X-Amzn-Trace-Id from AWS ALB, X-Forwarded-For from proxies).
        # These headers tell Cloudflare the request comes from a datacenter.
        # Uncomment when confirmed that stripping helps bypass anti-bot:
        #
        # _leaky_headers = {"x-amzn-trace-id", "x-forwarded-for", "x-envoy-external-address"}
        # async def _strip_leaky_headers(route):
        #     headers = {k: v for k, v in route.request.headers.items()
        #                if k.lower() not in _leaky_headers}
        #     await route.continue_(headers=headers)
        # await context.route("**/*", _strip_leaky_headers)

        return context

    def _make_config_signature(self, crawlerRunConfig: CrawlerRunConfig) -> str:
        """
        Hash ONLY the CrawlerRunConfig fields that affect browser context
        creation (create_browser_context) or context setup (setup_context).

        Whitelist approach: fields like css_selector, word_count_threshold,
        screenshot, verbose, etc. do NOT cause a new context to be created.
        """
        import json

        sig_dict = {}

        # Fields that flow into create_browser_context()
        pc = crawlerRunConfig.proxy_config
        if pc is not None:
            sig_dict["proxy_config"] = {
                "server": getattr(pc, "server", None),
                "username": getattr(pc, "username", None),
                "password": getattr(pc, "password", None),
            }
        else:
            sig_dict["proxy_config"] = None

        sig_dict["locale"] = crawlerRunConfig.locale
        sig_dict["timezone_id"] = crawlerRunConfig.timezone_id

        geo = crawlerRunConfig.geolocation
        if geo is not None:
            sig_dict["geolocation"] = {
                "latitude": geo.latitude,
                "longitude": geo.longitude,
                "accuracy": geo.accuracy,
            }
        else:
            sig_dict["geolocation"] = None

        # Fields that flow into setup_context() as init scripts
        sig_dict["override_navigator"] = crawlerRunConfig.override_navigator
        sig_dict["simulate_user"] = crawlerRunConfig.simulate_user
        sig_dict["magic"] = crawlerRunConfig.magic

        # Browser version — bumped on recycle to force new browser instance
        sig_dict["_browser_version"] = self._browser_version

        signature_json = json.dumps(sig_dict, sort_keys=True, default=str)
        return hashlib.sha256(signature_json.encode("utf-8")).hexdigest()

    def _evict_lru_context_locked(self):
        """
        If contexts exceed the limit, find the least-recently-used context
        with zero active crawls and remove it from all tracking dicts.

        MUST be called while holding self._contexts_lock.

        Returns the BrowserContext to close (caller closes it OUTSIDE the
        lock), or None if no eviction is needed or possible.
        """
        if len(self.contexts_by_config) <= self._max_contexts:
            return None

        # Sort candidates by last-used timestamp (oldest first)
        candidates = sorted(
            self._context_last_used.items(),
            key=lambda item: item[1],
        )
        for evict_sig, _ in candidates:
            if self._context_refcounts.get(evict_sig, 0) == 0:
                ctx = self.contexts_by_config.pop(evict_sig, None)
                self._context_refcounts.pop(evict_sig, None)
                self._context_last_used.pop(evict_sig, None)
                # Clean up stale page->sig mappings for evicted context
                stale_pages = [
                    p for p, s in self._page_to_sig.items() if s == evict_sig
                ]
                for p in stale_pages:
                    del self._page_to_sig[p]
                return ctx

        # All contexts are in active use — cannot evict
        return None

    async def _apply_stealth_to_page(self, page):
        """Apply stealth to a page if stealth mode is enabled"""
        if self._stealth_adapter:
            try:
                await self._stealth_adapter.apply_stealth(page)
            except Exception as e:
                if self.logger:
                    self.logger.warning(
                        message="Failed to apply stealth to page: {error}",
                        tag="STEALTH",
                        params={"error": str(e)}
                    )

    async def _get_page_by_target_id(self, context: BrowserContext, target_id: str):
        """
        Get an existing page by its CDP target ID.

        This is used when connecting to a pre-created browser context with an existing page.
        Playwright may not immediately see targets created via raw CDP commands, so we
        use CDP to get all targets and find the matching one.

        Args:
            context: The browser context to search in
            target_id: The CDP target ID to find

        Returns:
            Page object if found, None otherwise
        """
        try:
            # First check if Playwright already sees the page
            for page in context.pages:
                # Playwright's internal target ID might match
                if hasattr(page, '_impl_obj') and hasattr(page._impl_obj, '_target_id'):
                    if page._impl_obj._target_id == target_id:
                        return page

            # If not found, try using CDP to get targets
            if hasattr(self.browser, '_impl_obj') and hasattr(self.browser._impl_obj, '_connection'):
                cdp_session = await context.new_cdp_session(context.pages[0] if context.pages else None)
                if cdp_session:
                    try:
                        result = await cdp_session.send("Target.getTargets")
                        targets = result.get("targetInfos", [])
                        for target in targets:
                            if target.get("targetId") == target_id:
                                # Found the target - if it's a page type, we can use it
                                if target.get("type") == "page":
                                    # The page exists, let Playwright discover it
                                    await asyncio.sleep(0.1)
                                    # Refresh pages list
                                    if context.pages:
                                        return context.pages[0]
                    finally:
                        await cdp_session.detach()

            # Fallback: if there are any pages now, return the first one
            if context.pages:
                return context.pages[0]

            return None
        except Exception as e:
            if self.logger:
                self.logger.warning(
                    message="Failed to get page by target ID: {error}",
                    tag="BROWSER",
                    params={"error": str(e)}
                )
            return None

    async def get_page(self, crawlerRunConfig: CrawlerRunConfig):
        """
        Get a page for the given session ID, creating a new one if needed.

        Args:
            crawlerRunConfig (CrawlerRunConfig): Configuration object containing all browser settings

        Returns:
            (page, context): The Page and its BrowserContext
        """
        self._cleanup_expired_sessions()

        # If a session_id is provided and we already have it, reuse that page + context
        if crawlerRunConfig.session_id and crawlerRunConfig.session_id in self.sessions:
            context, page, _ = self.sessions[crawlerRunConfig.session_id]
            # Update last-used timestamp
            self.sessions[crawlerRunConfig.session_id] = (context, page, time.time())
            return page, context

        # If using a managed browser, just grab the shared default_context
        if self.config.use_managed_browser:
            # If create_isolated_context is True, create isolated contexts for concurrent crawls
            # Uses the same caching mechanism as non-CDP mode: cache context by config signature,
            # but always create a new page. This prevents navigation conflicts while allowing
            # context reuse for multiple URLs with the same config (e.g., batch/deep crawls).
            if self.config.create_isolated_context:
                config_signature = self._make_config_signature(crawlerRunConfig)
                to_close = None

                async with self._contexts_lock:
                    if config_signature in self.contexts_by_config:
                        context = self.contexts_by_config[config_signature]
                    else:
                        context = await self.create_browser_context(crawlerRunConfig)
                        await self.setup_context(context, crawlerRunConfig)
                        self.contexts_by_config[config_signature] = context
                        self._context_refcounts[config_signature] = 0
                        to_close = self._evict_lru_context_locked()

                    # Increment refcount INSIDE lock before releasing
                    self._context_refcounts[config_signature] = (
                        self._context_refcounts.get(config_signature, 0) + 1
                    )
                    self._context_last_used[config_signature] = time.monotonic()

                # Close evicted context OUTSIDE lock
                if to_close is not None:
                    try:
                        await to_close.close()
                    except Exception:
                        pass

                # Always create a new page for each crawl (isolation for navigation)
                try:
                    page = await context.new_page()
                except Exception:
                    async with self._contexts_lock:
                        if config_signature in self._context_refcounts:
                            self._context_refcounts[config_signature] = max(
                                0, self._context_refcounts[config_signature] - 1
                            )
                    raise
                await self._apply_stealth_to_page(page)
                self._page_to_sig[page] = config_signature
            elif self.config.storage_state:
                tmp_context = await self.create_browser_context(crawlerRunConfig)
                ctx = self.default_context        # default context, one window only
                ctx = await clone_runtime_state(tmp_context, ctx, crawlerRunConfig, self.config)
                # Close the temporary context — only needed as a clone source
                try:
                    await tmp_context.close()
                except Exception:
                    pass
                context = ctx  # so (page, context) return value is correct
                # Avoid concurrent new_page on shared persistent context
                # See GH-1198: context.pages can be empty under races
                async with self._page_lock:
                    page = await ctx.new_page()
                await self._apply_stealth_to_page(page)
            else:
                context = self.default_context

                # Handle pre-existing target case (for reconnecting to specific CDP targets)
                if self.config.browser_context_id and self.config.target_id:
                    page = await self._get_page_by_target_id(context, self.config.target_id)
                    if not page:
                        async with self._page_lock:
                            page = await context.new_page()
                            self._mark_page_in_use(page)
                        await self._apply_stealth_to_page(page)
                    else:
                        # Mark pre-existing target as in use
                        self._mark_page_in_use(page)
                else:
                    # For CDP connections (external browser), multiple Playwright connections
                    # create separate browser/context objects. Page reuse across connections
                    # isn't reliable because each connection sees different page objects.
                    # Always create new pages for CDP to avoid cross-connection race conditions.
                    if self.config.cdp_url and not self.config.use_managed_browser:
                        async with self._page_lock:
                            page = await context.new_page()
                            self._mark_page_in_use(page)
                        await self._apply_stealth_to_page(page)
                    else:
                        # For managed browsers (single process), page reuse is safe.
                        # Use lock to safely check for available pages and track usage.
                        # This prevents race conditions when multiple crawls run concurrently.
                        async with BrowserManager._get_global_lock():
                            pages = context.pages
                            pages_in_use = self._get_pages_in_use()
                            # Find first available page (exists and not currently in use)
                            available_page = next(
                                (p for p in pages if p not in pages_in_use),
                                None
                            )
                            if available_page:
                                page = available_page
                            else:
                                # No available pages - create a new one
                                page = await context.new_page()
                                await self._apply_stealth_to_page(page)
                            # Mark page as in use (global tracking)
                            self._mark_page_in_use(page)
        else:
            # Otherwise, check if we have an existing context for this config
            config_signature = self._make_config_signature(crawlerRunConfig)
            to_close = None

            async with self._contexts_lock:
                if config_signature in self.contexts_by_config:
                    context = self.contexts_by_config[config_signature]
                else:
                    # Create and setup a new context
                    context = await self.create_browser_context(crawlerRunConfig)
                    await self.setup_context(context, crawlerRunConfig)
                    self.contexts_by_config[config_signature] = context
                    self._context_refcounts[config_signature] = 0
                    to_close = self._evict_lru_context_locked()

                # Increment refcount INSIDE lock before releasing
                self._context_refcounts[config_signature] = (
                    self._context_refcounts.get(config_signature, 0) + 1
                )
                self._context_last_used[config_signature] = time.monotonic()

            # Close evicted context OUTSIDE lock
            if to_close is not None:
                try:
                    await to_close.close()
                except Exception:
                    pass

            # Create a new page from the chosen context
            try:
                page = await context.new_page()
            except Exception:
                async with self._contexts_lock:
                    if config_signature in self._context_refcounts:
                        self._context_refcounts[config_signature] = max(
                            0, self._context_refcounts[config_signature] - 1
                        )
                raise
            await self._apply_stealth_to_page(page)
            self._page_to_sig[page] = config_signature

        # If a session_id is specified, store this session so we can reuse later
        if crawlerRunConfig.session_id:
            self.sessions[crawlerRunConfig.session_id] = (context, page, time.time())

        self._pages_served += 1

        # Check if browser recycle threshold is hit — bump version for next requests
        # This happens AFTER incrementing counter so concurrent requests see correct count
        await self._maybe_bump_browser_version()

        return page, context

    async def kill_session(self, session_id: str):
        """
        Kill a browser session and clean up resources.

        Args:
            session_id (str): The session ID to kill.
        """
        if session_id in self.sessions:
            context, page, _ = self.sessions[session_id]
            self._release_page_from_use(page)
            # Decrement context refcount for the session's page
            should_close_context = False
            async with self._contexts_lock:
                sig = self._page_to_sig.pop(page, None)
                if sig is not None and sig in self._context_refcounts:
                    self._context_refcounts[sig] = max(
                        0, self._context_refcounts[sig] - 1
                    )
                    # Only close the context if no other pages are using it
                    # (refcount dropped to 0) AND we own the context (not managed)
                    if not self.config.use_managed_browser:
                        if self._context_refcounts.get(sig, 0) == 0:
                            self.contexts_by_config.pop(sig, None)
                            self._context_refcounts.pop(sig, None)
                            self._context_last_used.pop(sig, None)
                            should_close_context = True
            await page.close()
            if should_close_context:
                await context.close()
            del self.sessions[session_id]

    def release_page(self, page):
        """
        Release a page from the in-use tracking set (global tracking).
        Sync variant — does NOT decrement context refcount.
        """
        self._release_page_from_use(page)

    async def release_page_with_context(self, page):
        """
        Release a page and decrement its context's refcount under the lock.

        Should be called from the async crawl finally block instead of
        release_page() so the context lifecycle is properly tracked.
        """
        self._release_page_from_use(page)
        sig = None
        refcount = -1
        async with self._contexts_lock:
            sig = self._page_to_sig.pop(page, None)
            if sig is not None and sig in self._context_refcounts:
                self._context_refcounts[sig] = max(
                    0, self._context_refcounts[sig] - 1
                )
                refcount = self._context_refcounts[sig]

        # Check if this signature belongs to an old browser waiting to be cleaned up
        if sig is not None and refcount == 0:
            await self._maybe_cleanup_old_browser(sig)

    def _should_recycle(self) -> bool:
        """Check if page threshold reached for browser recycling."""
        limit = self.config.max_pages_before_recycle
        if limit <= 0:
            return False
        return self._pages_served >= limit

    async def _maybe_bump_browser_version(self):
        """Bump browser version if threshold reached, moving old browser to pending cleanup.

        New requests automatically get a new browser (via new signature).
        Old browser drains naturally and gets cleaned up when refcount hits 0.
        """
        if not self._should_recycle():
            return

        # Safety cap: wait if too many old browsers are draining
        while True:
            async with self._pending_cleanup_lock:
                # Re-check threshold under lock (another request may have bumped already)
                if not self._should_recycle():
                    return

                # Check safety cap
                if len(self._pending_cleanup) >= self._max_pending_browsers:
                    if self.logger:
                        self.logger.debug(
                            message="Waiting for old browser to drain (pending: {count})",
                            tag="BROWSER",
                            params={"count": len(self._pending_cleanup)},
                        )
                    self._cleanup_slot_available.clear()
                    # Release lock and wait
                else:
                    # We have a slot — do the bump inside this lock hold
                    old_version = self._browser_version
                    active_sigs = []
                    idle_sigs = []
                    async with self._contexts_lock:
                        for sig in list(self._context_refcounts.keys()):
                            if self._context_refcounts.get(sig, 0) > 0:
                                active_sigs.append(sig)
                            else:
                                idle_sigs.append(sig)

                    if self.logger:
                        self.logger.info(
                            message="Bumping browser version {old} -> {new} after {count} pages ({active} active, {idle} idle sigs)",
                            tag="BROWSER",
                            params={
                                "old": old_version,
                                "new": old_version + 1,
                                "count": self._pages_served,
                                "active": len(active_sigs),
                                "idle": len(idle_sigs),
                            },
                        )

                    # Only add sigs with active crawls to pending cleanup.
                    # Sigs with refcount 0 are cleaned up immediately below
                    # to avoid them being stuck in _pending_cleanup forever
                    # (no future release would trigger their cleanup).
                    done_event = asyncio.Event()
                    for sig in active_sigs:
                        self._pending_cleanup[sig] = {
                            "version": old_version,
                            "done": done_event,
                        }

                    # Bump version — new get_page() calls will create new contexts
                    self._browser_version += 1
                    self._pages_served = 0

                    # Clean up idle sigs immediately (outside pending_cleanup_lock below)
                    break  # exit while loop to do cleanup outside locks

            # Safety cap path: wait for a cleanup slot, then retry.
            # Timeout prevents permanent deadlock if stuck entries never drain.
            try:
                await asyncio.wait_for(
                    self._cleanup_slot_available.wait(), timeout=30.0
                )
            except asyncio.TimeoutError:
                # Force-clean any pending entries that have refcount 0
                # (they're stuck and will never drain naturally)
                async with self._pending_cleanup_lock:
                    stuck_sigs = [
                        s for s in list(self._pending_cleanup.keys())
                        if self._context_refcounts.get(s, 0) == 0
                    ]
                    for sig in stuck_sigs:
                        self._pending_cleanup.pop(sig, None)
                    if stuck_sigs:
                        if self.logger:
                            self.logger.warning(
                                message="Force-cleaned {count} stuck pending entries after timeout",
                                tag="BROWSER",
                                params={"count": len(stuck_sigs)},
                            )
                        # Clean up the stuck contexts
                        for sig in stuck_sigs:
                            async with self._contexts_lock:
                                context = self.contexts_by_config.pop(sig, None)
                                self._context_refcounts.pop(sig, None)
                                self._context_last_used.pop(sig, None)
                            if context is not None:
                                try:
                                    await context.close()
                                except Exception:
                                    pass
                        if len(self._pending_cleanup) < self._max_pending_browsers:
                            self._cleanup_slot_available.set()

        # Reached via break — clean up idle sigs immediately (outside locks)
        for sig in idle_sigs:
            async with self._contexts_lock:
                context = self.contexts_by_config.pop(sig, None)
                self._context_refcounts.pop(sig, None)
                self._context_last_used.pop(sig, None)
            if context is not None:
                try:
                    await context.close()
                except Exception:
                    pass
        if idle_sigs and self.logger:
            self.logger.debug(
                message="Immediately cleaned up {count} idle contexts from version {version}",
                tag="BROWSER",
                params={"count": len(idle_sigs), "version": old_version},
            )

    async def _maybe_cleanup_old_browser(self, sig: str):
        """Clean up an old browser's context if its refcount hit 0 and it's pending cleanup."""
        async with self._pending_cleanup_lock:
            if sig not in self._pending_cleanup:
                return  # Not an old browser signature

            cleanup_info = self._pending_cleanup.pop(sig)
            old_version = cleanup_info["version"]

            if self.logger:
                self.logger.debug(
                    message="Cleaning up context from browser version {version} (sig: {sig})",
                    tag="BROWSER",
                    params={"version": old_version, "sig": sig[:12]},
                )

            # Remove context from tracking
            async with self._contexts_lock:
                context = self.contexts_by_config.pop(sig, None)
                self._context_refcounts.pop(sig, None)
                self._context_last_used.pop(sig, None)

            # Close context outside locks
            if context is not None:
                try:
                    await context.close()
                except Exception:
                    pass

            # Check if any signatures from this old version remain
            remaining_old = [
                s for s, info in self._pending_cleanup.items()
                if info["version"] == old_version
            ]

            if not remaining_old:
                if self.logger:
                    self.logger.info(
                        message="All contexts from browser version {version} cleaned up",
                        tag="BROWSER",
                        params={"version": old_version},
                    )

            # Open a cleanup slot if we're below the cap
            if len(self._pending_cleanup) < self._max_pending_browsers:
                self._cleanup_slot_available.set()

    def _cleanup_expired_sessions(self):
        """Clean up expired sessions based on TTL."""
        current_time = time.time()
        expired_sessions = [
            sid
            for sid, (_, _, last_used) in self.sessions.items()
            if current_time - last_used > self.session_ttl
        ]
        for sid in expired_sessions:
            asyncio.create_task(self.kill_session(sid))

    async def close(self):
        """Close all browser resources and clean up."""
        # Cached CDP path: only clean up this instance's sessions/contexts,
        # then release the shared connection reference.
        if self._using_cached_cdp:
            session_ids = list(self.sessions.keys())
            for session_id in session_ids:
                await self.kill_session(session_id)
            for ctx in self.contexts_by_config.values():
                try:
                    await ctx.close()
                except Exception:
                    pass
            self.contexts_by_config.clear()
            self._context_refcounts.clear()
            self._context_last_used.clear()
            self._page_to_sig.clear()
            await _CDPConnectionCache.release(self.config.cdp_url)
            self.browser = None
            self.playwright = None
            self._using_cached_cdp = False
            return

        if self.config.cdp_url:
            # When using external CDP, we don't own the browser process.
            # If cdp_cleanup_on_close is True, properly disconnect from the browser
            # and clean up Playwright resources. This frees the browser for other clients.
            if self.config.cdp_cleanup_on_close:
                # First close all sessions (pages)
                session_ids = list(self.sessions.keys())
                for session_id in session_ids:
                    await self.kill_session(session_id)

                # Close all contexts we created
                for ctx in self.contexts_by_config.values():
                    try:
                        await ctx.close()
                    except Exception:
                        pass
                self.contexts_by_config.clear()
                self._context_refcounts.clear()
                self._context_last_used.clear()
                self._page_to_sig.clear()

                # Disconnect from browser (doesn't terminate it, just releases connection)
                if self.browser:
                    try:
                        await self.browser.close()
                    except Exception as e:
                        if self.logger:
                            self.logger.debug(
                                message="Error disconnecting from CDP browser: {error}",
                                tag="BROWSER",
                                params={"error": str(e)}
                            )
                    self.browser = None
                    # Allow time for CDP connection to fully release before another client connects
                    if self.config.cdp_close_delay > 0:
                        await asyncio.sleep(self.config.cdp_close_delay)

                # Stop Playwright instance to prevent memory leaks
                if self.playwright:
                    await self.playwright.stop()
                    self.playwright = None
            return

        # ── Persistent context launched via launch_persistent_context ──
        if self._launched_persistent:
            session_ids = list(self.sessions.keys())
            for session_id in session_ids:
                await self.kill_session(session_id)
            for ctx in self.contexts_by_config.values():
                try:
                    await ctx.close()
                except Exception:
                    pass
            self.contexts_by_config.clear()
            self._context_refcounts.clear()
            self._context_last_used.clear()
            self._page_to_sig.clear()

            # Closing the persistent context also terminates the browser
            if self.default_context:
                try:
                    await self.default_context.close()
                except Exception:
                    pass
                self.default_context = None

            if self.playwright:
                await self.playwright.stop()
                self.playwright = None
            self._launched_persistent = False
            return

        if self.config.sleep_on_close:
            await asyncio.sleep(0.5)

        session_ids = list(self.sessions.keys())
        for session_id in session_ids:
            await self.kill_session(session_id)

        # Now close all contexts we created. This reclaims memory from ephemeral contexts.
        for ctx in self.contexts_by_config.values():
            try:
                await ctx.close()
            except Exception as e:
                self.logger.error(
                    message="Error closing context: {error}",
                    tag="ERROR",
                    params={"error": str(e)}
                )
        self.contexts_by_config.clear()
        self._context_refcounts.clear()
        self._context_last_used.clear()
        self._page_to_sig.clear()

        if self.browser:
            await self.browser.close()
            self.browser = None

        if self.managed_browser:
            await asyncio.sleep(0.5)
            await self.managed_browser.cleanup()
            self.managed_browser = None

        if self.playwright:
            await self.playwright.stop()
            self.playwright = None

```


## File: docs/examples/quickstart.py


```py
import os, sys

from crawl4ai import LLMConfig

sys.path.append(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

import asyncio
import time
import json
import re
from typing import Dict
from bs4 import BeautifulSoup
from pydantic import BaseModel, Field
from crawl4ai import AsyncWebCrawler, CacheMode, BrowserConfig, CrawlerRunConfig
from crawl4ai.markdown_generation_strategy import DefaultMarkdownGenerator
from crawl4ai.content_filter_strategy import PruningContentFilter
from crawl4ai import (
    JsonCssExtractionStrategy,
    LLMExtractionStrategy,
)

__location__ = os.path.realpath(os.path.join(os.getcwd(), os.path.dirname(__file__)))

print("Crawl4AI: Advanced Web Crawling and Data Extraction")
print("GitHub Repository: https://github.com/unclecode/crawl4ai")
print("Twitter: @unclecode")
print("Website: https://crawl4ai.com")


# Basic Example - Simple Crawl
async def simple_crawl():
    print("\n--- Basic Usage ---")
    browser_config = BrowserConfig(headless=True)
    crawler_config = CrawlerRunConfig(cache_mode=CacheMode.BYPASS)

    async with AsyncWebCrawler(config=browser_config) as crawler:
        result = await crawler.arun(
            url="https://www.nbcnews.com/business", config=crawler_config
        )
        print(result.markdown[:500])


async def clean_content():
    crawler_config = CrawlerRunConfig(
        cache_mode=CacheMode.BYPASS,
        excluded_tags=["nav", "footer", "aside"],
        remove_overlay_elements=True,
        markdown_generator=DefaultMarkdownGenerator(
            content_filter=PruningContentFilter(
                threshold=0.48, threshold_type="fixed", min_word_threshold=0
            ),
            options={"ignore_links": True},
        ),
    )
    async with AsyncWebCrawler() as crawler:
        result = await crawler.arun(
            url="https://en.wikipedia.org/wiki/Apple",
            config=crawler_config,
        )
        full_markdown_length = len(result.markdown.raw_markdown)
        fit_markdown_length = len(result.markdown.fit_markdown)
        print(f"Full Markdown Length: {full_markdown_length}")
        print(f"Fit Markdown Length: {fit_markdown_length}")


async def link_analysis():
    crawler_config = CrawlerRunConfig(
        cache_mode=CacheMode.ENABLED,
        exclude_external_links=True,
        exclude_social_media_links=True,
    )
    async with AsyncWebCrawler() as crawler:
        result = await crawler.arun(
            url="https://www.nbcnews.com/business",
            config=crawler_config,
        )
        print(f"Found {len(result.links['internal'])} internal links")
        print(f"Found {len(result.links['external'])} external links")

        for link in result.links["internal"][:5]:
            print(f"Href: {link['href']}\nText: {link['text']}\n")


# JavaScript Execution Example
async def simple_example_with_running_js_code():
    print("\n--- Executing JavaScript and Using CSS Selectors ---")

    browser_config = BrowserConfig(headless=True, java_script_enabled=True)

    crawler_config = CrawlerRunConfig(
        cache_mode=CacheMode.BYPASS,
        js_code="const loadMoreButton = Array.from(document.querySelectorAll('button')).find(button => button.textContent.includes('Load More')); loadMoreButton && loadMoreButton.click();",
        # wait_for="() => { return Array.from(document.querySelectorAll('article.tease-card')).length > 10; }"
    )

    async with AsyncWebCrawler(config=browser_config) as crawler:
        result = await crawler.arun(
            url="https://www.nbcnews.com/business", config=crawler_config
        )
        print(result.markdown[:500])


# CSS Selector Example
async def simple_example_with_css_selector():
    print("\n--- Using CSS Selectors ---")
    browser_config = BrowserConfig(headless=True)
    crawler_config = CrawlerRunConfig(
        cache_mode=CacheMode.BYPASS, css_selector=".wide-tease-item__description"
    )

    async with AsyncWebCrawler(config=browser_config) as crawler:
        result = await crawler.arun(
            url="https://www.nbcnews.com/business", config=crawler_config
        )
        print(result.markdown[:500])


async def media_handling():
    crawler_config = CrawlerRunConfig(
        cache_mode=CacheMode.BYPASS, exclude_external_images=True, screenshot=True
    )
    async with AsyncWebCrawler() as crawler:
        result = await crawler.arun(
            url="https://www.nbcnews.com/business", config=crawler_config
        )
        for img in result.media["images"][:5]:
            print(f"Image URL: {img['src']}, Alt: {img['alt']}, Score: {img['score']}")


async def custom_hook_workflow(verbose=True):
    async with AsyncWebCrawler() as crawler:
        # Set a 'before_goto' hook to run custom code just before navigation
        crawler.crawler_strategy.set_hook(
            "before_goto",
            lambda page, context: print("[Hook] Preparing to navigate..."),
        )

        # Perform the crawl operation
        result = await crawler.arun(url="https://crawl4ai.com")
        print(result.markdown.raw_markdown[:500].replace("\n", " -- "))


# Proxy Example
async def use_proxy():
    print("\n--- Using a Proxy ---")
    browser_config = BrowserConfig(
        headless=True,
        proxy_config={
            "server": "http://proxy.example.com:8080",
            "username": "username",
            "password": "password",
        },
    )
    crawler_config = CrawlerRunConfig(cache_mode=CacheMode.BYPASS)

    async with AsyncWebCrawler(config=browser_config) as crawler:
        result = await crawler.arun(
            url="https://www.nbcnews.com/business", config=crawler_config
        )
        if result.success:
            print(result.markdown[:500])


# Screenshot Example
async def capture_and_save_screenshot(url: str, output_path: str):
    browser_config = BrowserConfig(headless=True)
    crawler_config = CrawlerRunConfig(cache_mode=CacheMode.BYPASS, screenshot=True)

    async with AsyncWebCrawler(config=browser_config) as crawler:
        result = await crawler.arun(url=url, config=crawler_config)

        if result.success and result.screenshot:
            import base64

            screenshot_data = base64.b64decode(result.screenshot)
            with open(output_path, "wb") as f:
                f.write(screenshot_data)
            print(f"Screenshot saved successfully to {output_path}")
        else:
            print("Failed to capture screenshot")


# LLM Extraction Example
class OpenAIModelFee(BaseModel):
    model_name: str = Field(..., description="Name of the OpenAI model.")
    input_fee: str = Field(..., description="Fee for input token for the OpenAI model.")
    output_fee: str = Field(
        ..., description="Fee for output token for the OpenAI model."
    )


async def extract_structured_data_using_llm(
    provider: str, api_token: str = None, extra_headers: Dict[str, str] = None
):
    print(f"\n--- Extracting Structured Data with {provider} ---")

    if api_token is None and provider != "ollama":
        print(f"API token is required for {provider}. Skipping this example.")
        return

    browser_config = BrowserConfig(headless=True)

    extra_args = {"temperature": 0, "top_p": 0.9, "max_tokens": 2000}
    if extra_headers:
        extra_args["extra_headers"] = extra_headers

    crawler_config = CrawlerRunConfig(
        cache_mode=CacheMode.BYPASS,
        word_count_threshold=1,
        page_timeout=80000,
        extraction_strategy=LLMExtractionStrategy(
            llm_config=LLMConfig(provider=provider,api_token=api_token),
            schema=OpenAIModelFee.model_json_schema(),
            extraction_type="schema",
            instruction="""From the crawled content, extract all mentioned model names along with their fees for input and output tokens. 
            Do not miss any models in the entire content.""",
            extra_args=extra_args,
        ),
    )

    async with AsyncWebCrawler(config=browser_config) as crawler:
        result = await crawler.arun(
            url="https://openai.com/api/pricing/", config=crawler_config
        )
        print(result.extracted_content)


# CSS Extraction Example
async def extract_structured_data_using_css_extractor():
    print("\n--- Using JsonCssExtractionStrategy for Fast Structured Output ---")
    schema = {
        "name": "KidoCode Courses",
        "baseSelector": "section.charge-methodology .framework-collection-item.w-dyn-item",
        "fields": [
            {
                "name": "section_title",
                "selector": "h3.heading-50",
                "type": "text",
            },
            {
                "name": "section_description",
                "selector": ".charge-content",
                "type": "text",
            },
            {
                "name": "course_name",
                "selector": ".text-block-93",
                "type": "text",
            },
            {
                "name": "course_description",
                "selector": ".course-content-text",
                "type": "text",
            },
            {
                "name": "course_icon",
                "selector": ".image-92",
                "type": "attribute",
                "attribute": "src",
            },
        ],
    }

    browser_config = BrowserConfig(headless=True, java_script_enabled=True)

    js_click_tabs = """
    (async () => {
        const tabs = document.querySelectorAll("section.charge-methodology .tabs-menu-3 > div");
        for(let tab of tabs) {
            tab.scrollIntoView();
            tab.click();
            await new Promise(r => setTimeout(r, 500));
        }
    })();
    """

    crawler_config = CrawlerRunConfig(
        cache_mode=CacheMode.BYPASS,
        extraction_strategy=JsonCssExtractionStrategy(schema),
        js_code=[js_click_tabs],
        delay_before_return_html=1
    )

    async with AsyncWebCrawler(config=browser_config) as crawler:
        result = await crawler.arun(
            url="https://www.kidocode.com/degrees/technology", config=crawler_config
        )

        companies = json.loads(result.extracted_content)
        print(f"Successfully extracted {len(companies)} companies")
        print(json.dumps(companies[0], indent=2))


# Dynamic Content Examples - Method 1
async def crawl_dynamic_content_pages_method_1():
    print("\n--- Advanced Multi-Page Crawling with JavaScript Execution ---")
    first_commit = ""

    async def on_execution_started(page, **kwargs):
        nonlocal first_commit
        try:
            while True:
                await page.wait_for_selector("li.Box-sc-g0xbh4-0 h4")
                commit = await page.query_selector("li.Box-sc-g0xbh4-0 h4")
                commit = await commit.evaluate("(element) => element.textContent")
                commit = re.sub(r"\s+", "", commit)
                if commit and commit != first_commit:
                    first_commit = commit
                    break
                await asyncio.sleep(0.5)
        except Exception as e:
            print(f"Warning: New content didn't appear after JavaScript execution: {e}")

    browser_config = BrowserConfig(headless=False, java_script_enabled=True)

    async with AsyncWebCrawler(config=browser_config) as crawler:
        crawler.crawler_strategy.set_hook("on_execution_started", on_execution_started)

        url = "https://github.com/microsoft/TypeScript/commits/main"
        session_id = "typescript_commits_session"
        all_commits = []

        js_next_page = """
        const button = document.querySelector('a[data-testid="pagination-next-button"]');
        if (button) button.click();
        """

        for page in range(3):
            crawler_config = CrawlerRunConfig(
                cache_mode=CacheMode.BYPASS,
                css_selector="li.Box-sc-g0xbh4-0",
                js_code=js_next_page if page > 0 else None,
                js_only=page > 0,
                session_id=session_id,
            )

            result = await crawler.arun(url=url, config=crawler_config)
            assert result.success, f"Failed to crawl page {page + 1}"

            soup = BeautifulSoup(result.cleaned_html, "html.parser")
            commits = soup.select("li")
            all_commits.extend(commits)

            print(f"Page {page + 1}: Found {len(commits)} commits")

        print(f"Successfully crawled {len(all_commits)} commits across 3 pages")


# Dynamic Content Examples - Method 2
async def crawl_dynamic_content_pages_method_2():
    print("\n--- Advanced Multi-Page Crawling with JavaScript Execution ---")

    browser_config = BrowserConfig(headless=False, java_script_enabled=True)

    js_next_page_and_wait = """
    (async () => {
        const getCurrentCommit = () => {
            const commits = document.querySelectorAll('li.Box-sc-g0xbh4-0 h4');
            return commits.length > 0 ? commits[0].textContent.trim() : null;
        };

        const initialCommit = getCurrentCommit();
        const button = document.querySelector('a[data-testid="pagination-next-button"]');
        if (button) button.click();

        while (true) {
            await new Promise(resolve => setTimeout(resolve, 100));
            const newCommit = getCurrentCommit();
            if (newCommit && newCommit !== initialCommit) {
                break;
            }
        }
    })();
    """

    schema = {
        "name": "Commit Extractor",
        "baseSelector": "li.Box-sc-g0xbh4-0",
        "fields": [
            {
                "name": "title",
                "selector": "h4.markdown-title",
                "type": "text",
                "transform": "strip",
            },
        ],
    }

    async with AsyncWebCrawler(config=browser_config) as crawler:
        url = "https://github.com/microsoft/TypeScript/commits/main"
        session_id = "typescript_commits_session"
        all_commits = []

        extraction_strategy = JsonCssExtractionStrategy(schema)

        for page in range(3):
            crawler_config = CrawlerRunConfig(
                cache_mode=CacheMode.BYPASS,
                css_selector="li.Box-sc-g0xbh4-0",
                extraction_strategy=extraction_strategy,
                js_code=js_next_page_and_wait if page > 0 else None,
                js_only=page > 0,
                session_id=session_id,
            )

            result = await crawler.arun(url=url, config=crawler_config)
            assert result.success, f"Failed to crawl page {page + 1}"

            commits = json.loads(result.extracted_content)
            all_commits.extend(commits)
            print(f"Page {page + 1}: Found {len(commits)} commits")

        print(f"Successfully crawled {len(all_commits)} commits across 3 pages")


async def cosine_similarity_extraction():
    from crawl4ai import CosineStrategy
    crawl_config = CrawlerRunConfig(
        cache_mode=CacheMode.BYPASS,
        extraction_strategy=CosineStrategy(
            word_count_threshold=10,
            max_dist=0.2,  # Maximum distance between two words
            linkage_method="ward",  # Linkage method for hierarchical clustering (ward, complete, average, single)
            top_k=3,  # Number of top keywords to extract
            sim_threshold=0.3,  # Similarity threshold for clustering
            semantic_filter="McDonald's economic impact, American consumer trends",  # Keywords to filter the content semantically using embeddings
            verbose=True,
        ),
    )
    async with AsyncWebCrawler() as crawler:
        result = await crawler.arun(
            url="https://www.nbcnews.com/business/consumer/how-mcdonalds-e-coli-crisis-inflation-politics-reflect-american-story-rcna177156",
            config=crawl_config,
        )
        print(json.loads(result.extracted_content)[:5])


# Browser Comparison
async def crawl_custom_browser_type():
    print("\n--- Browser Comparison ---")

    # Firefox
    browser_config_firefox = BrowserConfig(browser_type="firefox", headless=True)
    start = time.time()
    async with AsyncWebCrawler(config=browser_config_firefox) as crawler:
        result = await crawler.arun(
            url="https://www.example.com",
            config=CrawlerRunConfig(cache_mode=CacheMode.BYPASS),
        )
        print("Firefox:", time.time() - start)
        print(result.markdown[:500])

    # WebKit
    browser_config_webkit = BrowserConfig(browser_type="webkit", headless=True)
    start = time.time()
    async with AsyncWebCrawler(config=browser_config_webkit) as crawler:
        result = await crawler.arun(
            url="https://www.example.com",
            config=CrawlerRunConfig(cache_mode=CacheMode.BYPASS),
        )
        print("WebKit:", time.time() - start)
        print(result.markdown[:500])

    # Chromium (default)
    browser_config_chromium = BrowserConfig(browser_type="chromium", headless=True)
    start = time.time()
    async with AsyncWebCrawler(config=browser_config_chromium) as crawler:
        result = await crawler.arun(
            url="https://www.example.com",
            config=CrawlerRunConfig(cache_mode=CacheMode.BYPASS),
        )
        print("Chromium:", time.time() - start)
        print(result.markdown[:500])


# Anti-Bot and User Simulation
async def crawl_with_user_simulation():
    browser_config = BrowserConfig(
        headless=True,
        user_agent_mode="random",
        user_agent_generator_config={"device_type": "mobile", "os_type": "android"},
    )

    crawler_config = CrawlerRunConfig(
        cache_mode=CacheMode.BYPASS,
        magic=True,
        simulate_user=True,
        override_navigator=True,
    )

    async with AsyncWebCrawler(config=browser_config) as crawler:
        result = await crawler.arun(url="YOUR-URL-HERE", config=crawler_config)
        print(result.markdown)


async def ssl_certification():
    # Configure crawler to fetch SSL certificate
    config = CrawlerRunConfig(
        fetch_ssl_certificate=True,
        cache_mode=CacheMode.BYPASS,  # Bypass cache to always get fresh certificates
    )

    async with AsyncWebCrawler() as crawler:
        result = await crawler.arun(url="https://example.com", config=config)

        if result.success and result.ssl_certificate:
            cert = result.ssl_certificate

            tmp_dir = os.path.join(__location__, "tmp")
            os.makedirs(tmp_dir, exist_ok=True)

            # 1. Access certificate properties directly
            print("\nCertificate Information:")
            print(f"Issuer: {cert.issuer.get('CN', '')}")
            print(f"Valid until: {cert.valid_until}")
            print(f"Fingerprint: {cert.fingerprint}")

            # 2. Export certificate in different formats
            cert.to_json(os.path.join(tmp_dir, "certificate.json"))  # For analysis
            print("\nCertificate exported to:")
            print(f"- JSON: {os.path.join(tmp_dir, 'certificate.json')}")

            pem_data = cert.to_pem(
                os.path.join(tmp_dir, "certificate.pem")
            )  # For web servers
            print(f"- PEM: {os.path.join(tmp_dir, 'certificate.pem')}")

            der_data = cert.to_der(
                os.path.join(tmp_dir, "certificate.der")
            )  # For Java apps
            print(f"- DER: {os.path.join(tmp_dir, 'certificate.der')}")


# Main execution
async def main():
    # Basic examples
    await simple_crawl()
    await simple_example_with_running_js_code()
    await simple_example_with_css_selector()

    # Advanced examples
    await extract_structured_data_using_css_extractor()
    await extract_structured_data_using_llm(
        "openai/gpt-4o", os.getenv("OPENAI_API_KEY")
    )
    await crawl_dynamic_content_pages_method_1()
    await crawl_dynamic_content_pages_method_2()

    # Browser comparisons
    await crawl_custom_browser_type()

    # Screenshot example
    await capture_and_save_screenshot(
        "https://www.example.com",
        os.path.join(__location__, "tmp/example_screenshot.jpg")
    )


if __name__ == "__main__":
    asyncio.run(main())

```


## File: docs/examples/quickstart_examples_set_1.py


```py
import asyncio
import os
import json
import base64
from pathlib import Path
from typing import List
from crawl4ai import ProxyConfig

from crawl4ai import AsyncWebCrawler, CrawlerRunConfig, CacheMode, CrawlResult
from crawl4ai import RoundRobinProxyStrategy
from crawl4ai import JsonCssExtractionStrategy, LLMExtractionStrategy
from crawl4ai import LLMConfig
from crawl4ai import PruningContentFilter, BM25ContentFilter
from crawl4ai import DefaultMarkdownGenerator
from crawl4ai import BFSDeepCrawlStrategy, DomainFilter, FilterChain
from crawl4ai import BrowserConfig

__cur_dir__ = Path(__file__).parent

async def demo_basic_crawl():
    """Basic web crawling with markdown generation"""
    print("\n=== 1. Basic Web Crawling ===")
    async with AsyncWebCrawler(config = BrowserConfig(
        viewport_height=800,
        viewport_width=1200,
        headless=True,
        verbose=True,
    )) as crawler:
        results: List[CrawlResult] = await crawler.arun(
            url="https://news.ycombinator.com/"
        )

        for i, result in enumerate(results):
            print(f"Result {i + 1}:")
            print(f"Success: {result.success}")
            if result.success:
                print(f"Markdown length: {len(result.markdown.raw_markdown)} chars")
                print(f"First 100 chars: {result.markdown.raw_markdown[:100]}...")
            else:
                print("Failed to crawl the URL")

async def demo_parallel_crawl():
    """Crawl multiple URLs in parallel"""
    print("\n=== 2. Parallel Crawling ===")

    urls = [
        "https://news.ycombinator.com/",
        "https://example.com/",
        "https://httpbin.org/html",
    ]

    async with AsyncWebCrawler() as crawler:
        results: List[CrawlResult] = await crawler.arun_many(
            urls=urls,
        )

        print(f"Crawled {len(results)} URLs in parallel:")
        for i, result in enumerate(results):
            print(
                f"  {i + 1}. {result.url} - {'Success' if result.success else 'Failed'}"
            )

async def demo_fit_markdown():
    """Generate focused markdown with LLM content filter"""
    print("\n=== 3. Fit Markdown with LLM Content Filter ===")

    async with AsyncWebCrawler() as crawler:
        result: CrawlResult = await crawler.arun(
            url = "https://en.wikipedia.org/wiki/Python_(programming_language)",
            config=CrawlerRunConfig(
                markdown_generator=DefaultMarkdownGenerator(
                    content_filter=PruningContentFilter()
                )
            ),
        )

        # Print stats and save the fit markdown
        print(f"Raw: {len(result.markdown.raw_markdown)} chars")
        print(f"Fit: {len(result.markdown.fit_markdown)} chars")

async def demo_llm_structured_extraction_no_schema():
    # Create a simple LLM extraction strategy (no schema required)
    extraction_strategy = LLMExtractionStrategy(
        llm_config=LLMConfig(
            provider="groq/qwen-2.5-32b",
            api_token="env:GROQ_API_KEY",
        ),
        instruction="This is news.ycombinator.com, extract all news, and for each, I want title, source url, number of comments.",
        extract_type="schema",
        schema="{title: string, url: string, comments: int}",
        extra_args={
            "temperature": 0.0,
            "max_tokens": 4096,
        },
        verbose=True,
    )

    config = CrawlerRunConfig(extraction_strategy=extraction_strategy)

    async with AsyncWebCrawler() as crawler:
        results: List[CrawlResult] = await crawler.arun(
            "https://news.ycombinator.com/", config=config
        )

        for result in results:
            print(f"URL: {result.url}")
            print(f"Success: {result.success}")
            if result.success:
                data = json.loads(result.extracted_content)
                print(json.dumps(data, indent=2))
            else:
                print("Failed to extract structured data")

async def demo_css_structured_extraction_no_schema():
    """Extract structured data using CSS selectors"""
    print("\n=== 5. CSS-Based Structured Extraction ===")
    # Sample HTML for schema generation (one-time cost)
    sample_html = """
<div class="body-post clear">
    <a class="story-link" href="https://thehackernews.com/2025/04/malicious-python-packages-on-pypi.html">
        <div class="clear home-post-box cf">
            <div class="home-img clear">
                <div class="img-ratio">
                    <img alt="..." src="...">
                </div>
            </div>
            <div class="clear home-right">
                <h2 class="home-title">Malicious Python Packages on PyPI Downloaded 39,000+ Times, Steal Sensitive Data</h2>
                <div class="item-label">
                    <span class="h-datetime"><i class="icon-font icon-calendar"></i>Apr 05, 2025</span>
                    <span class="h-tags">Malware / Supply Chain Attack</span>
                </div>
                <div class="home-desc"> Cybersecurity researchers have...</div>
            </div>
        </div>
    </a>
</div>
    """

    # Check if schema file exists
    schema_file_path = f"{__cur_dir__}/tmp/schema.json"
    if os.path.exists(schema_file_path):
        with open(schema_file_path, "r") as f:
            schema = json.load(f)
    else:
        # Generate schema using LLM (one-time setup)
        schema = JsonCssExtractionStrategy.generate_schema(
            html=sample_html,
            llm_config=LLMConfig(
                provider="groq/qwen-2.5-32b",
                api_token="env:GROQ_API_KEY",
            ),
            query="From https://thehackernews.com/, I have shared a sample of one news div with a title, date, and description. Please generate a schema for this news div.",
        )

    print(f"Generated schema: {json.dumps(schema, indent=2)}")
    # Save the schema to a file , and use it for future extractions, in result for such extraction you will call LLM once
    with open(f"{__cur_dir__}/tmp/schema.json", "w") as f:
        json.dump(schema, f, indent=2)

    # Create no-LLM extraction strategy with the generated schema
    extraction_strategy = JsonCssExtractionStrategy(schema)
    config = CrawlerRunConfig(extraction_strategy=extraction_strategy)

    # Use the fast CSS extraction (no LLM calls during extraction)
    async with AsyncWebCrawler() as crawler:
        results: List[CrawlResult] = await crawler.arun(
            "https://thehackernews.com", config=config
        )

        for result in results:
            print(f"URL: {result.url}")
            print(f"Success: {result.success}")
            if result.success:
                data = json.loads(result.extracted_content)
                print(json.dumps(data, indent=2))
            else:
                print("Failed to extract structured data")

async def demo_deep_crawl():
    """Deep crawling with BFS strategy"""
    print("\n=== 6. Deep Crawling ===")

    filter_chain = FilterChain([DomainFilter(allowed_domains=["crawl4ai.com"])])

    deep_crawl_strategy = BFSDeepCrawlStrategy(
        max_depth=1, max_pages=5, filter_chain=filter_chain
    )

    async with AsyncWebCrawler() as crawler:
        results: List[CrawlResult] = await crawler.arun(
            url="https://docs.crawl4ai.com",
            config=CrawlerRunConfig(deep_crawl_strategy=deep_crawl_strategy),
        )

        print(f"Deep crawl returned {len(results)} pages:")
        for i, result in enumerate(results):
            depth = result.metadata.get("depth", "unknown")
            print(f"  {i + 1}. {result.url} (Depth: {depth})")

async def demo_js_interaction():
    """Execute JavaScript to load more content"""
    print("\n=== 7. JavaScript Interaction ===")

    # A simple page that needs JS to reveal content
    async with AsyncWebCrawler(config=BrowserConfig(headless=False)) as crawler:
        # Initial load

        news_schema = {
            "name": "news",
            "baseSelector": "tr.athing",
            "fields": [
                {
                    "name": "title",
                    "selector": "span.titleline",
                    "type": "text",
                }
            ],
        }
        results: List[CrawlResult] = await crawler.arun(
            url="https://news.ycombinator.com",
            config=CrawlerRunConfig(
                session_id="hn_session",  # Keep session
                extraction_strategy=JsonCssExtractionStrategy(schema=news_schema),
            ),
        )

        news = []
        for result in results:
            if result.success:
                data = json.loads(result.extracted_content)
                news.extend(data)
                print(json.dumps(data, indent=2))
            else:
                print("Failed to extract structured data")

        print(f"Initial items: {len(news)}")

        # Click "More" link
        more_config = CrawlerRunConfig(
            js_code="document.querySelector('a.morelink').click();",
            js_only=True,  # Continue in same page
            session_id="hn_session",  # Keep session
            extraction_strategy=JsonCssExtractionStrategy(
                schema=news_schema,
            ),
        )

        result: List[CrawlResult] = await crawler.arun(
            url="https://news.ycombinator.com", config=more_config
        )

        # Extract new items
        for result in results:
            if result.success:
                data = json.loads(result.extracted_content)
                news.extend(data)
                print(json.dumps(data, indent=2))
            else:
                print("Failed to extract structured data")
        print(f"Total items: {len(news)}")

async def demo_media_and_links():
    """Extract media and links from a page"""
    print("\n=== 8. Media and Links Extraction ===")

    async with AsyncWebCrawler() as crawler:
        result: List[CrawlResult] = await crawler.arun("https://en.wikipedia.org/wiki/Main_Page")

        for i, result in enumerate(result):
            # Extract and save all images
            images = result.media.get("images", [])
            print(f"Found {len(images)} images")

            # Extract and save all links (internal and external)
            internal_links = result.links.get("internal", [])
            external_links = result.links.get("external", [])
            print(f"Found {len(internal_links)} internal links")
            print(f"Found {len(external_links)} external links")

            # Print some of the images and links
            for image in images[:3]:
                print(f"Image: {image['src']}")
            for link in internal_links[:3]:
                print(f"Internal link: {link['href']}")
            for link in external_links[:3]:
                print(f"External link: {link['href']}")

            # # Save everything to files
            with open(f"{__cur_dir__}/tmp/images.json", "w") as f:
                json.dump(images, f, indent=2)

            with open(f"{__cur_dir__}/tmp/links.json", "w") as f:
                json.dump(
                    {"internal": internal_links, "external": external_links},
                    f,
                    indent=2,
                )

async def demo_screenshot_and_pdf():
    """Capture screenshot and PDF of a page"""
    print("\n=== 9. Screenshot and PDF Capture ===")

    async with AsyncWebCrawler() as crawler:
        result: List[CrawlResult] = await crawler.arun(
            # url="https://example.com",
            url="https://en.wikipedia.org/wiki/Giant_anteater",
            config=CrawlerRunConfig(screenshot=True, pdf=True),
        )

        for i, result in enumerate(result):
            # if result.screenshot_data:
            if result.screenshot:
                # Save screenshot
                screenshot_path = f"{__cur_dir__}/tmp/example_screenshot.png"
                with open(screenshot_path, "wb") as f:
                    f.write(base64.b64decode(result.screenshot))
                print(f"Screenshot saved to {screenshot_path}")

            # if result.pdf_data:
            if result.pdf:
                # Save PDF
                pdf_path = f"{__cur_dir__}/tmp/example.pdf"
                with open(pdf_path, "wb") as f:
                    f.write(result.pdf)
                print(f"PDF saved to {pdf_path}")

async def demo_proxy_rotation():
    """Proxy rotation for multiple requests"""
    print("\n=== 10. Proxy Rotation ===")

    # Example proxies (replace with real ones)
    proxies = [
        ProxyConfig(server="http://proxy1.example.com:8080"),
        ProxyConfig(server="http://proxy2.example.com:8080"),
    ]

    proxy_strategy = RoundRobinProxyStrategy(proxies)

    print(f"Using {len(proxies)} proxies in rotation")
    print(
        "Note: This example uses placeholder proxies - replace with real ones to test"
    )

    async with AsyncWebCrawler() as crawler:
        config = CrawlerRunConfig(
            proxy_rotation_strategy=proxy_strategy
        )

        # In a real scenario, these would be run and the proxies would rotate
        print("In a real scenario, requests would rotate through the available proxies")

async def demo_raw_html_and_file():
    """Process raw HTML and local files"""
    print("\n=== 11. Raw HTML and Local Files ===")

    raw_html = """
    <html><body>
        <h1>Sample Article</h1>
        <p>This is sample content for testing Crawl4AI's raw HTML processing.</p>
    </body></html>
    """

    # Save to file
    file_path = Path("docs/examples/tmp/sample.html").absolute()
    with open(file_path, "w") as f:
        f.write(raw_html)

    async with AsyncWebCrawler() as crawler:
        # Crawl raw HTML
        raw_result = await crawler.arun(
            url="raw:" + raw_html, config=CrawlerRunConfig(cache_mode=CacheMode.BYPASS)
        )
        print("Raw HTML processing:")
        print(f"  Markdown: {raw_result.markdown.raw_markdown[:50]}...")

        # Crawl local file
        file_result = await crawler.arun(
            url=f"file://{file_path}",
            config=CrawlerRunConfig(cache_mode=CacheMode.BYPASS),
        )
        print("\nLocal file processing:")
        print(f"  Markdown: {file_result.markdown.raw_markdown[:50]}...")

    # Clean up
    os.remove(file_path)
    print(f"Processed both raw HTML and local file ({file_path})")

async def main():
    """Run all demo functions sequentially"""
    print("=== Comprehensive Crawl4AI Demo ===")
    print("Note: Some examples require API keys or other configurations")

    # Run all demos
    await demo_basic_crawl()
    await demo_parallel_crawl()
    await demo_fit_markdown()
    await demo_llm_structured_extraction_no_schema()
    await demo_css_structured_extraction_no_schema()
    await demo_deep_crawl()
    await demo_js_interaction()
    await demo_media_and_links()
    await demo_screenshot_and_pdf()
    # # await demo_proxy_rotation()
    await demo_raw_html_and_file()

    # Clean up any temp files that may have been created
    print("\n=== Demo Complete ===")
    print("Check for any generated files (screenshots, PDFs) in the current directory")

if __name__ == "__main__":
    asyncio.run(main())

```


## File: docs/examples/dispatcher_example.py


```py
import asyncio
import time
from rich import print
from rich.table import Table
from crawl4ai import (
    AsyncWebCrawler,
    BrowserConfig,
    CrawlerRunConfig,
    MemoryAdaptiveDispatcher,
    SemaphoreDispatcher,
    RateLimiter,
    CrawlerMonitor,
    DisplayMode,
    CacheMode,
    LXMLWebScrapingStrategy,
)


async def memory_adaptive(urls, browser_config, run_config):
    """Memory adaptive crawler with monitoring"""
    start = time.perf_counter()
    async with AsyncWebCrawler(config=browser_config) as crawler:
        dispatcher = MemoryAdaptiveDispatcher(
            memory_threshold_percent=70.0,
            max_session_permit=10,
            monitor=CrawlerMonitor(
                max_visible_rows=15, display_mode=DisplayMode.DETAILED
            ),
        )
        results = await crawler.arun_many(
            urls, config=run_config, dispatcher=dispatcher
        )
    duration = time.perf_counter() - start
    return len(results), duration


async def memory_adaptive_with_rate_limit(urls, browser_config, run_config):
    """Memory adaptive crawler with rate limiting"""
    start = time.perf_counter()
    async with AsyncWebCrawler(config=browser_config) as crawler:
        dispatcher = MemoryAdaptiveDispatcher(
            memory_threshold_percent=95.0,
            max_session_permit=10,
            rate_limiter=RateLimiter(
                base_delay=(1.0, 2.0), max_delay=30.0, max_retries=2
            ),
            monitor=CrawlerMonitor(
                max_visible_rows=15, display_mode=DisplayMode.DETAILED
            ),
        )
        results = await crawler.arun_many(
            urls, config=run_config, dispatcher=dispatcher
        )
    duration = time.perf_counter() - start
    return len(results), duration


async def semaphore(urls, browser_config, run_config):
    """Basic semaphore crawler"""
    start = time.perf_counter()
    async with AsyncWebCrawler(config=browser_config) as crawler:
        dispatcher = SemaphoreDispatcher(
            semaphore_count=5,
            monitor=CrawlerMonitor(
                max_visible_rows=15, display_mode=DisplayMode.DETAILED
            ),
        )
        results = await crawler.arun_many(
            urls, config=run_config, dispatcher=dispatcher
        )
    duration = time.perf_counter() - start
    return len(results), duration


async def semaphore_with_rate_limit(urls, browser_config, run_config):
    """Semaphore crawler with rate limiting"""
    start = time.perf_counter()
    async with AsyncWebCrawler(config=browser_config) as crawler:
        dispatcher = SemaphoreDispatcher(
            semaphore_count=5,
            rate_limiter=RateLimiter(
                base_delay=(1.0, 2.0), max_delay=30.0, max_retries=2
            ),
            monitor=CrawlerMonitor(
                max_visible_rows=15, display_mode=DisplayMode.DETAILED
            ),
        )
        results = await crawler.arun_many(
            urls, config=run_config, dispatcher=dispatcher
        )
    duration = time.perf_counter() - start
    return len(results), duration


def create_performance_table(results):
    """Creates a rich table showing performance results"""
    table = Table(title="Crawler Strategy Performance Comparison")
    table.add_column("Strategy", style="cyan")
    table.add_column("URLs Crawled", justify="right", style="green")
    table.add_column("Time (seconds)", justify="right", style="yellow")
    table.add_column("URLs/second", justify="right", style="magenta")

    sorted_results = sorted(results.items(), key=lambda x: x[1][1])

    for strategy, (urls_crawled, duration) in sorted_results:
        urls_per_second = urls_crawled / duration
        table.add_row(
            strategy, str(urls_crawled), f"{duration:.2f}", f"{urls_per_second:.2f}"
        )

    return table


async def main():
    urls = [f"https://example.com/page{i}" for i in range(1, 40)]
    browser_config = BrowserConfig(headless=True, verbose=False)
    run_config = CrawlerRunConfig(cache_mode=CacheMode.BYPASS, scraping_strategy=LXMLWebScrapingStrategy())

    results = {
        "Memory Adaptive": await memory_adaptive(urls, browser_config, run_config),
        # "Memory Adaptive + Rate Limit": await memory_adaptive_with_rate_limit(
        #     urls, browser_config, run_config
        # ),
        # "Semaphore": await semaphore(urls, browser_config, run_config),
        # "Semaphore + Rate Limit": await semaphore_with_rate_limit(
        #     urls, browser_config, run_config
        # ),
    }

    table = create_performance_table(results)
    print("\nPerformance Summary:")
    print(table)


if __name__ == "__main__":
    asyncio.run(main())

```


## File: docs/examples/hello_world.py


```py
import asyncio
from crawl4ai import (
    AsyncWebCrawler,
    BrowserConfig,
    CrawlerRunConfig,
    DefaultMarkdownGenerator,
    PruningContentFilter,
    CrawlResult
)


async def main():
    browser_config = BrowserConfig(
        headless=False,
        verbose=True,
    )
    async with AsyncWebCrawler(config=browser_config) as crawler:
        crawler_config = CrawlerRunConfig(
            markdown_generator=DefaultMarkdownGenerator(
                content_filter=PruningContentFilter()
            ),
        )
        result: CrawlResult = await crawler.arun(
            url="https://www.helloworld.org", config=crawler_config
        )
        print(result.markdown.raw_markdown[:500])

if __name__ == "__main__":
    asyncio.run(main())

```


## File: docs/examples/hooks_example.py


```py
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode
from playwright.async_api import Page, BrowserContext


async def main():
    print("🔗 Hooks Example: Demonstrating different hook use cases")

    # Configure browser settings
    browser_config = BrowserConfig(headless=True)

    # Configure crawler settings
    crawler_run_config = CrawlerRunConfig(
        js_code="window.scrollTo(0, document.body.scrollHeight);",
        wait_for="body",
        cache_mode=CacheMode.BYPASS,
    )

    # Create crawler instance
    crawler = AsyncWebCrawler(config=browser_config)

    # Define and set hook functions
    async def on_browser_created(browser, context: BrowserContext, **kwargs):
        """Hook called after the browser is created"""
        print("[HOOK] on_browser_created - Browser is ready!")
        # Example: Set a cookie that will be used for all requests
        return browser

    async def on_page_context_created(page: Page, context: BrowserContext, **kwargs):
        """Hook called after a new page and context are created"""
        print("[HOOK] on_page_context_created - New page created!")
        # Example: Set default viewport size
        await context.add_cookies(
            [
                {
                    "name": "session_id",
                    "value": "example_session",
                    "domain": ".example.com",
                    "path": "/",
                }
            ]
        )
        await page.set_viewport_size({"width": 1080, "height": 800})
        return page

    async def on_user_agent_updated(
        page: Page, context: BrowserContext, user_agent: str, **kwargs
    ):
        """Hook called when the user agent is updated"""
        print(f"[HOOK] on_user_agent_updated - New user agent: {user_agent}")
        return page

    async def on_execution_started(page: Page, context: BrowserContext, **kwargs):
        """Hook called after custom JavaScript execution"""
        print("[HOOK] on_execution_started - Custom JS executed!")
        return page

    async def before_goto(page: Page, context: BrowserContext, url: str, **kwargs):
        """Hook called before navigating to each URL"""
        print(f"[HOOK] before_goto - About to visit: {url}")
        # Example: Add custom headers for the request
        await page.set_extra_http_headers({"Custom-Header": "my-value"})
        return page

    async def after_goto(
        page: Page, context: BrowserContext, url: str, response: dict, **kwargs
    ):
        """Hook called after navigating to each URL"""
        print(f"[HOOK] after_goto - Successfully loaded: {url}")
        # Example: Wait for a specific element to be loaded
        try:
            await page.wait_for_selector(".content", timeout=1000)
            print("Content element found!")
        except:
            print("Content element not found, continuing anyway")
        return page

    async def before_retrieve_html(page: Page, context: BrowserContext, **kwargs):
        """Hook called before retrieving the HTML content"""
        print("[HOOK] before_retrieve_html - About to get HTML content")
        # Example: Scroll to bottom to trigger lazy loading
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight);")
        return page

    async def before_return_html(
        page: Page, context: BrowserContext, html: str, **kwargs
    ):
        """Hook called before returning the HTML content"""
        print(f"[HOOK] before_return_html - Got HTML content (length: {len(html)})")
        # Example: You could modify the HTML content here if needed
        return page

    # Set all the hooks
    crawler.crawler_strategy.set_hook("on_browser_created", on_browser_created)
    crawler.crawler_strategy.set_hook(
        "on_page_context_created", on_page_context_created
    )
    crawler.crawler_strategy.set_hook("on_user_agent_updated", on_user_agent_updated)
    crawler.crawler_strategy.set_hook("on_execution_started", on_execution_started)
    crawler.crawler_strategy.set_hook("before_goto", before_goto)
    crawler.crawler_strategy.set_hook("after_goto", after_goto)
    crawler.crawler_strategy.set_hook("before_retrieve_html", before_retrieve_html)
    crawler.crawler_strategy.set_hook("before_return_html", before_return_html)

    await crawler.start()

    # Example usage: crawl a simple website
    url = "https://example.com"
    result = await crawler.arun(url, config=crawler_run_config)
    print(f"\nCrawled URL: {result.url}")
    print(f"HTML length: {len(result.html)}")

    await crawler.close()


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())

```


## File: crawl4ai/deep_crawling/__init__.py


```py
# deep_crawling/__init__.py
from .base_strategy import DeepCrawlDecorator, DeepCrawlStrategy
from .bfs_strategy import BFSDeepCrawlStrategy
from .bff_strategy import BestFirstCrawlingStrategy
from .dfs_strategy import DFSDeepCrawlStrategy
from .filters import (
    FilterChain,
    ContentTypeFilter,
    DomainFilter,
    URLFilter,
    URLPatternFilter,
    FilterStats,
    ContentRelevanceFilter,
    SEOFilter
)
from .scorers import (
    KeywordRelevanceScorer,
    URLScorer,
    CompositeScorer,
    DomainAuthorityScorer,
    FreshnessScorer,
    PathDepthScorer,
    ContentTypeScorer
)

__all__ = [
    "DeepCrawlDecorator",
    "DeepCrawlStrategy",
    "BFSDeepCrawlStrategy",
    "BestFirstCrawlingStrategy",
    "DFSDeepCrawlStrategy",
    "FilterChain",
    "ContentTypeFilter",
    "DomainFilter",
    "URLFilter",
    "URLPatternFilter",
    "FilterStats",
    "ContentRelevanceFilter",
    "SEOFilter",
    "KeywordRelevanceScorer",
    "URLScorer",
    "CompositeScorer",
    "DomainAuthorityScorer",
    "FreshnessScorer",
    "PathDepthScorer",
    "ContentTypeScorer",
]

```


## File: crawl4ai/deep_crawling/base_strategy.py


```py
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import AsyncGenerator, Optional, Set, List, Dict
from functools import wraps
from contextvars import ContextVar
from ..types import AsyncWebCrawler, CrawlerRunConfig, CrawlResult, RunManyReturn


class DeepCrawlDecorator:
    """Decorator that adds deep crawling capability to arun method."""
    deep_crawl_active = ContextVar("deep_crawl_active", default=False)
    
    def __init__(self, crawler: AsyncWebCrawler): 
        self.crawler = crawler

    def __call__(self, original_arun):
        @wraps(original_arun)
        async def wrapped_arun(url: str, config: CrawlerRunConfig = None, **kwargs):
            # If deep crawling is already active, call the original method to avoid recursion.
            if config and config.deep_crawl_strategy and not self.deep_crawl_active.get():
                token = self.deep_crawl_active.set(True)
                # Await the arun call to get the actual result object.
                result_obj = await config.deep_crawl_strategy.arun(
                    crawler=self.crawler,
                    start_url=url,
                    config=config
                )
                if config.stream:
                    async def result_wrapper():
                        try:
                            async for result in result_obj:
                                yield result
                        finally:
                            self.deep_crawl_active.reset(token)
                    return result_wrapper()
                else:
                    try:
                        return result_obj
                    finally:
                        self.deep_crawl_active.reset(token)
            return await original_arun(url, config=config, **kwargs)
        return wrapped_arun

class DeepCrawlStrategy(ABC):
    """
    Abstract base class for deep crawling strategies.
    
    Core functions:
      - arun: Main entry point that returns an async generator of CrawlResults.
      - shutdown: Clean up resources.
      - can_process_url: Validate a URL and decide whether to process it.
      - _process_links: Extract and process links from a CrawlResult.
    """

    @abstractmethod
    async def _arun_batch(
        self,
        start_url: str,
        crawler: AsyncWebCrawler,
        config: CrawlerRunConfig,
    ) -> List[CrawlResult]:
        """
        Batch (non-streaming) mode:
        Processes one BFS level at a time, then yields all the results.
        """
        pass

    @abstractmethod
    async def _arun_stream(
        self,
        start_url: str,
        crawler: AsyncWebCrawler,
        config: CrawlerRunConfig,
    ) -> AsyncGenerator[CrawlResult, None]:
        """
        Streaming mode:
        Processes one BFS level at a time and yields results immediately as they arrive.
        """
        pass
    
    async def arun(
        self,
        start_url: str,
        crawler: AsyncWebCrawler,
        config: Optional[CrawlerRunConfig] = None,
    ) -> RunManyReturn:
        """
        Traverse the given URL using the specified crawler.
        
        Args:
            start_url (str): The URL from which to start crawling.
            crawler (AsyncWebCrawler): The crawler instance to use.
            crawler_run_config (Optional[CrawlerRunConfig]): Crawler configuration.
        
        Returns:
            Union[CrawlResultT, List[CrawlResultT], AsyncGenerator[CrawlResultT, None]]
        """
        if config is None:
            raise ValueError("CrawlerRunConfig must be provided")

        if config.stream:
            return self._arun_stream(start_url, crawler, config)
        else:
            return await self._arun_batch(start_url, crawler, config)

    def __call__(self, start_url: str, crawler: AsyncWebCrawler, config: CrawlerRunConfig):
        return self.arun(start_url, crawler, config)

    @abstractmethod
    async def shutdown(self) -> None:
        """
        Clean up resources used by the deep crawl strategy.
        """
        pass

    @abstractmethod
    async def can_process_url(self, url: str, depth: int) -> bool:
        """
        Validate the URL format and apply custom filtering logic.
        
        Args:
            url (str): The URL to validate.
            depth (int): The current depth in the crawl.
        
        Returns:
            bool: True if the URL should be processed, False otherwise.
        """
        pass

    @abstractmethod
    async def link_discovery(
        self,
        result: CrawlResult,
        source_url: str,
        current_depth: int,
        visited: Set[str],
        next_level: List[tuple],
        depths: Dict[str, int],
    ) -> None:
        """
        Extract and process links from the given crawl result.
        
        This method should:
          - Validate each extracted URL using can_process_url.
          - Optionally score URLs.
          - Append valid URLs (and their parent references) to the next_level list.
          - Update the depths dictionary with the new depth for each URL.
        
        Args:
            result (CrawlResult): The result from a crawl operation.
            source_url (str): The URL from which this result was obtained.
            current_depth (int): The depth at which the source URL was processed.
            visited (Set[str]): Set of already visited URLs.
            next_level (List[tuple]): List of tuples (url, parent_url) for the next BFS level.
            depths (Dict[str, int]): Mapping of URLs to their current depth.
        """
        pass


```


## File: crawl4ai/deep_crawling/bff_strategy.py


```py
# best_first_crawling_strategy.py
import asyncio
import logging
from datetime import datetime
from typing import AsyncGenerator, Optional, Set, Dict, List, Tuple, Any, Callable, Awaitable, Union
from urllib.parse import urlparse

from ..models import TraversalStats
from .filters import FilterChain
from .scorers import URLScorer
from . import DeepCrawlStrategy

from ..types import AsyncWebCrawler, CrawlerRunConfig, CrawlResult, RunManyReturn
from ..utils import normalize_url_for_deep_crawl

from math import inf as infinity

# Configurable batch size for processing items from the priority queue
BATCH_SIZE = 10


class BestFirstCrawlingStrategy(DeepCrawlStrategy):
    """
    Best-First Crawling Strategy using a priority queue.
    
    This strategy prioritizes URLs based on their score, ensuring that higher-value
    pages are crawled first. It reimplements the core traversal loop to use a priority
    queue while keeping URL validation and link discovery consistent with our design.
    
    Core methods:
      - arun: Returns either a list (batch mode) or an async generator (stream mode).
      - _arun_best_first: Core generator that uses a priority queue to yield CrawlResults.
      - can_process_url: Validates URLs and applies filtering (inherited behavior).
      - link_discovery: Extracts and validates links from a CrawlResult.
    """
    def __init__(
        self,
        max_depth: int,
        filter_chain: FilterChain = FilterChain(),
        url_scorer: Optional[URLScorer] = None,
        include_external: bool = False,
        score_threshold: float = -infinity,
        max_pages: int = infinity,
        logger: Optional[logging.Logger] = None,
        # Optional resume/callback parameters for crash recovery
        resume_state: Optional[Dict[str, Any]] = None,
        on_state_change: Optional[Callable[[Dict[str, Any]], Awaitable[None]]] = None,
        # Optional cancellation callback - checked before each URL is processed
        should_cancel: Optional[Callable[[], Union[bool, Awaitable[bool]]]] = None,
    ):
        self.max_depth = max_depth
        self.filter_chain = filter_chain
        self.url_scorer = url_scorer
        self.include_external = include_external
        self.score_threshold = score_threshold
        self.max_pages = max_pages
        # self.logger = logger or logging.getLogger(__name__)
        # Ensure logger is always a Logger instance, not a dict from serialization
        if isinstance(logger, logging.Logger):
            self.logger = logger
        else:
            # Create a new logger if logger is None, dict, or any other non-Logger type
            self.logger = logging.getLogger(__name__)
        self.stats = TraversalStats(start_time=datetime.now())
        self._cancel_event = asyncio.Event()
        self._pages_crawled = 0
        # Store for use in arun methods
        self._resume_state = resume_state
        self._on_state_change = on_state_change
        self._should_cancel = should_cancel
        self._last_state: Optional[Dict[str, Any]] = None
        # Shadow list for queue items (only used when on_state_change is set)
        self._queue_shadow: Optional[List[Tuple[float, int, str, Optional[str]]]] = None

    async def can_process_url(self, url: str, depth: int) -> bool:
        """
        Validate the URL format and apply filtering.
        For the starting URL (depth 0), filtering is bypassed.
        """
        try:
            parsed = urlparse(url)
            if not parsed.scheme or not parsed.netloc:
                raise ValueError("Missing scheme or netloc")
            if parsed.scheme not in ("http", "https"):
                raise ValueError("Invalid scheme")
            if "." not in parsed.netloc:
                raise ValueError("Invalid domain")
        except Exception as e:
            self.logger.warning(f"Invalid URL: {url}, error: {e}")
            return False

        if depth != 0 and not await self.filter_chain.apply(url):
            return False

        return True

    def cancel(self) -> None:
        """
        Cancel the crawl. Thread-safe, can be called from any context.

        The crawl will stop before processing the next URL. The current URL
        being processed (if any) will complete before the crawl stops.
        """
        self._cancel_event.set()

    @property
    def cancelled(self) -> bool:
        """
        Check if the crawl was/is cancelled. Thread-safe.

        Returns:
            True if the crawl has been cancelled, False otherwise.
        """
        return self._cancel_event.is_set()

    async def _check_cancellation(self) -> bool:
        """
        Check if crawl should be cancelled.

        Handles both internal cancel flag and external should_cancel callback.
        Supports both sync and async callbacks.

        Returns:
            True if crawl should be cancelled, False otherwise.
        """
        if self._cancel_event.is_set():
            return True

        if self._should_cancel:
            try:
                # Handle both sync and async callbacks
                result = self._should_cancel()
                if asyncio.iscoroutine(result):
                    result = await result

                if result:
                    self._cancel_event.set()
                    self.stats.end_time = datetime.now()
                    return True
            except Exception as e:
                # Fail-open: log warning and continue crawling
                self.logger.warning(f"should_cancel callback error: {e}")

        return False

    async def link_discovery(
        self,
        result: CrawlResult,
        source_url: str,
        current_depth: int,
        visited: Set[str],
        next_links: List[Tuple[str, Optional[str]]],
        depths: Dict[str, int],
    ) -> None:
        """
        Extract links from the crawl result, validate them, and append new URLs
        (with their parent references) to next_links.
        Also updates the depths dictionary.
        """
        new_depth = current_depth + 1
        if new_depth > self.max_depth:
            return
            
        # If we've reached the max pages limit, don't discover new links
        remaining_capacity = self.max_pages - self._pages_crawled
        if remaining_capacity <= 0:
            self.logger.info(f"Max pages limit ({self.max_pages}) reached, stopping link discovery")
            return

        # Retrieve internal links; include external links if enabled.
        links = result.links.get("internal", [])
        if self.include_external:
            links += result.links.get("external", [])

        # If we have more links than remaining capacity, limit how many we'll process
        valid_links = []
        for link in links:
            url = link.get("href")
            base_url = normalize_url_for_deep_crawl(url, source_url)
            if base_url in visited:
                continue
            if not await self.can_process_url(base_url, new_depth):
                self.stats.urls_skipped += 1
                continue
                
            valid_links.append(base_url)
            
        # Record the new depths and add to next_links
        for url in valid_links:
            depths[url] = new_depth
            next_links.append((url, source_url))

    async def _arun_best_first(
        self,
        start_url: str,
        crawler: AsyncWebCrawler,
        config: CrawlerRunConfig,
    ) -> AsyncGenerator[CrawlResult, None]:
        """
        Core best-first crawl method using a priority queue.

        The queue items are tuples of (score, depth, url, parent_url). Lower scores
        are treated as higher priority. URLs are processed in batches for efficiency.
        """
        # Reset cancel event for strategy reuse
        self._cancel_event = asyncio.Event()

        queue: asyncio.PriorityQueue = asyncio.PriorityQueue()

        # Conditional state initialization for resume support
        if self._resume_state:
            visited = set(self._resume_state.get("visited", []))
            depths = dict(self._resume_state.get("depths", {}))
            self._pages_crawled = self._resume_state.get("pages_crawled", 0)
            # Restore queue from saved items
            queue_items = self._resume_state.get("queue_items", [])
            for item in queue_items:
                await queue.put((item["score"], item["depth"], item["url"], item["parent_url"]))
            # Initialize shadow list if callback is set
            if self._on_state_change:
                self._queue_shadow = [
                    (item["score"], item["depth"], item["url"], item["parent_url"])
                    for item in queue_items
                ]
        else:
            # Original initialization
            initial_score = self.url_scorer.score(start_url) if self.url_scorer else 0
            await queue.put((-initial_score, 0, start_url, None))
            visited: Set[str] = set()
            depths: Dict[str, int] = {start_url: 0}
            # Initialize shadow list if callback is set
            if self._on_state_change:
                self._queue_shadow = [(-initial_score, 0, start_url, None)]

        while not queue.empty() and not self._cancel_event.is_set():
            # Stop if we've reached the max pages limit
            if self._pages_crawled >= self.max_pages:
                self.logger.info(f"Max pages limit ({self.max_pages}) reached, stopping crawl")
                break

            # Check external cancellation callback before processing this batch
            if await self._check_cancellation():
                self.logger.info("Crawl cancelled by user")
                break

            # Calculate how many more URLs we can process in this batch
            remaining = self.max_pages - self._pages_crawled
            batch_size = min(BATCH_SIZE, remaining)
            if batch_size <= 0:
                # No more pages to crawl
                self.logger.info(f"Max pages limit ({self.max_pages}) reached, stopping crawl")
                break
                
            batch: List[Tuple[float, int, str, Optional[str]]] = []
            # Retrieve up to BATCH_SIZE items from the priority queue.
            for _ in range(BATCH_SIZE):
                if queue.empty():
                    break
                item = await queue.get()
                # Remove from shadow list if tracking
                if self._on_state_change and self._queue_shadow is not None:
                    try:
                        self._queue_shadow.remove(item)
                    except ValueError:
                        pass  # Item may have been removed already
                score, depth, url, parent_url = item
                if url in visited:
                    continue
                visited.add(url)
                batch.append(item)

            if not batch:
                continue

            # Process the current batch of URLs.
            urls = [item[2] for item in batch]
            batch_config = config.clone(deep_crawl_strategy=None, stream=True)
            stream_gen = await crawler.arun_many(urls=urls, config=batch_config)
            async for result in stream_gen:
                result_url = result.url
                # Find the corresponding tuple from the batch.
                corresponding = next((item for item in batch if item[2] == result_url), None)
                if not corresponding:
                    continue
                score, depth, url, parent_url = corresponding
                result.metadata = result.metadata or {}
                result.metadata["depth"] = depth
                result.metadata["parent_url"] = parent_url
                result.metadata["score"] = -score
                
                # Count only successful crawls toward max_pages limit
                if result.success:
                    self._pages_crawled += 1
                    # Check if we've reached the limit during batch processing
                    if self._pages_crawled >= self.max_pages:
                        self.logger.info(f"Max pages limit ({self.max_pages}) reached during batch, stopping crawl")
                        break  # Exit the generator
                
                yield result
                
                # Only discover links from successful crawls
                if result.success:
                    # Discover new links from this result
                    new_links: List[Tuple[str, Optional[str]]] = []
                    await self.link_discovery(result, result_url, depth, visited, new_links, depths)
                    
                    for new_url, new_parent in new_links:
                        new_depth = depths.get(new_url, depth + 1)
                        new_score = self.url_scorer.score(new_url) if self.url_scorer else 0
                        # Skip URLs with scores below the threshold
                        if new_score < self.score_threshold:
                            self.logger.debug(
                                f"URL {new_url} skipped: score {new_score} below threshold {self.score_threshold}"
                            )
                            self.stats.urls_skipped += 1
                            continue
                        queue_item = (-new_score, new_depth, new_url, new_parent)
                        await queue.put(queue_item)
                        # Add to shadow list if tracking
                        if self._on_state_change and self._queue_shadow is not None:
                            self._queue_shadow.append(queue_item)

                    # Capture state after EACH URL processed (if callback set)
                    if self._on_state_change and self._queue_shadow is not None:
                        state = {
                            "strategy_type": "best_first",
                            "visited": list(visited),
                            "queue_items": [
                                {"score": s, "depth": d, "url": u, "parent_url": p}
                                for s, d, u, p in self._queue_shadow
                            ],
                            "depths": depths,
                            "pages_crawled": self._pages_crawled,
                            "cancelled": self._cancel_event.is_set(),
                        }
                        self._last_state = state
                        await self._on_state_change(state)

        # Final state update if cancelled
        if self._cancel_event.is_set() and self._on_state_change and self._queue_shadow is not None:
            state = {
                "strategy_type": "best_first",
                "visited": list(visited),
                "queue_items": [
                    {"score": s, "depth": d, "url": u, "parent_url": p}
                    for s, d, u, p in self._queue_shadow
                ],
                "depths": depths,
                "pages_crawled": self._pages_crawled,
                "cancelled": True,
            }
            self._last_state = state
            await self._on_state_change(state)

    async def _arun_batch(
        self,
        start_url: str,
        crawler: AsyncWebCrawler,
        config: CrawlerRunConfig,
    ) -> List[CrawlResult]:
        """
        Best-first crawl in batch mode.
        
        Aggregates all CrawlResults into a list.
        """
        results: List[CrawlResult] = []
        async for result in self._arun_best_first(start_url, crawler, config):
            results.append(result)
        return results

    async def _arun_stream(
        self,
        start_url: str,
        crawler: AsyncWebCrawler,
        config: CrawlerRunConfig,
    ) -> AsyncGenerator[CrawlResult, None]:
        """
        Best-first crawl in streaming mode.
        
        Yields CrawlResults as they become available.
        """
        async for result in self._arun_best_first(start_url, crawler, config):
            yield result

    async def arun(
        self,
        start_url: str,
        crawler: AsyncWebCrawler,
        config: Optional[CrawlerRunConfig] = None,
    ) -> "RunManyReturn":
        """
        Main entry point for best-first crawling.
        
        Returns either a list (batch mode) or an async generator (stream mode)
        of CrawlResults.
        """
        if config is None:
            raise ValueError("CrawlerRunConfig must be provided")
        if config.stream:
            return self._arun_stream(start_url, crawler, config)
        else:
            return await self._arun_batch(start_url, crawler, config)

    async def shutdown(self) -> None:
        """
        Signal cancellation and clean up resources.
        """
        self._cancel_event.set()
        self.stats.end_time = datetime.now()

    def export_state(self) -> Optional[Dict[str, Any]]:
        """
        Export current crawl state for external persistence.

        Note: This returns the last captured state. For real-time state,
        use the on_state_change callback.

        Returns:
            Dict with strategy state, or None if no state captured yet.
        """
        return self._last_state

```


## File: crawl4ai/deep_crawling/bfs_strategy.py


```py
# bfs_deep_crawl_strategy.py
import asyncio
import logging
from datetime import datetime
from typing import AsyncGenerator, Optional, Set, Dict, List, Tuple, Any, Callable, Awaitable, Union
from urllib.parse import urlparse

from ..models import TraversalStats
from .filters import FilterChain
from .scorers import URLScorer
from . import DeepCrawlStrategy  
from ..types import AsyncWebCrawler, CrawlerRunConfig, CrawlResult
from ..utils import normalize_url_for_deep_crawl, efficient_normalize_url_for_deep_crawl
from math import inf as infinity

class BFSDeepCrawlStrategy(DeepCrawlStrategy):
    """
    Breadth-First Search deep crawling strategy.
    
    Core functions:
      - arun: Main entry point; splits execution into batch or stream modes.
      - link_discovery: Extracts, filters, and (if needed) scores the outgoing URLs.
      - can_process_url: Validates URL format and applies the filter chain.
    """
    def __init__(
        self,
        max_depth: int,
        filter_chain: FilterChain = FilterChain(),
        url_scorer: Optional[URLScorer] = None,
        include_external: bool = False,
        score_threshold: float = -infinity,
        max_pages: int = infinity,
        logger: Optional[logging.Logger] = None,
        # Optional resume/callback parameters for crash recovery
        resume_state: Optional[Dict[str, Any]] = None,
        on_state_change: Optional[Callable[[Dict[str, Any]], Awaitable[None]]] = None,
        # Optional cancellation callback - checked before each URL is processed
        should_cancel: Optional[Callable[[], Union[bool, Awaitable[bool]]]] = None,
    ):
        self.max_depth = max_depth
        self.filter_chain = filter_chain
        self.url_scorer = url_scorer
        self.include_external = include_external
        self.score_threshold = score_threshold
        self.max_pages = max_pages
        # self.logger = logger or logging.getLogger(__name__)
        # Ensure logger is always a Logger instance, not a dict from serialization
        if isinstance(logger, logging.Logger):
            self.logger = logger
        else:
            # Create a new logger if logger is None, dict, or any other non-Logger type
            self.logger = logging.getLogger(__name__)
        self.stats = TraversalStats(start_time=datetime.now())
        self._cancel_event = asyncio.Event()
        self._pages_crawled = 0
        # Store for use in arun methods
        self._resume_state = resume_state
        self._on_state_change = on_state_change
        self._should_cancel = should_cancel
        self._last_state: Optional[Dict[str, Any]] = None

    async def can_process_url(self, url: str, depth: int) -> bool:
        """
        Validates the URL and applies the filter chain.
        For the start URL (depth 0) filtering is bypassed.
        """
        try:
            parsed = urlparse(url)
            if not parsed.scheme or not parsed.netloc:
                raise ValueError("Missing scheme or netloc")
            if parsed.scheme not in ("http", "https"):
                raise ValueError("Invalid scheme")
            if "." not in parsed.netloc:
                raise ValueError("Invalid domain")
        except Exception as e:
            self.logger.warning(f"Invalid URL: {url}, error: {e}")
            return False

        if depth != 0 and not await self.filter_chain.apply(url):
            return False

        return True

    def cancel(self) -> None:
        """
        Cancel the crawl. Thread-safe, can be called from any context.

        The crawl will stop before processing the next URL. The current URL
        being processed (if any) will complete before the crawl stops.
        """
        self._cancel_event.set()

    @property
    def cancelled(self) -> bool:
        """
        Check if the crawl was/is cancelled. Thread-safe.

        Returns:
            True if the crawl has been cancelled, False otherwise.
        """
        return self._cancel_event.is_set()

    async def _check_cancellation(self) -> bool:
        """
        Check if crawl should be cancelled.

        Handles both internal cancel flag and external should_cancel callback.
        Supports both sync and async callbacks.

        Returns:
            True if crawl should be cancelled, False otherwise.
        """
        if self._cancel_event.is_set():
            return True

        if self._should_cancel:
            try:
                # Handle both sync and async callbacks
                result = self._should_cancel()
                if asyncio.iscoroutine(result):
                    result = await result

                if result:
                    self._cancel_event.set()
                    self.stats.end_time = datetime.now()
                    return True
            except Exception as e:
                # Fail-open: log warning and continue crawling
                self.logger.warning(f"should_cancel callback error: {e}")

        return False

    async def link_discovery(
        self,
        result: CrawlResult,
        source_url: str,
        current_depth: int,
        visited: Set[str],
        next_level: List[Tuple[str, Optional[str]]],
        depths: Dict[str, int],
    ) -> None:
        """
        Extracts links from the crawl result, validates and scores them, and
        prepares the next level of URLs.
        Each valid URL is appended to next_level as a tuple (url, parent_url)
        and its depth is tracked.
        """            
        next_depth = current_depth + 1
        if next_depth > self.max_depth:
            return

        # If we've reached the max pages limit, don't discover new links
        remaining_capacity = self.max_pages - self._pages_crawled
        if remaining_capacity <= 0:
            self.logger.info(f"Max pages limit ({self.max_pages}) reached, stopping link discovery")
            return

        # Get internal links and, if enabled, external links.
        links = result.links.get("internal", [])
        if self.include_external:
            links += result.links.get("external", [])

        valid_links = []
        
        # First collect all valid links
        for link in links:
            url = link.get("href")
            # Strip URL fragments to avoid duplicate crawling
            # base_url = url.split('#')[0] if url else url
            base_url = normalize_url_for_deep_crawl(url, source_url)
            if base_url in visited:
                continue
            if not await self.can_process_url(base_url, next_depth):
                self.stats.urls_skipped += 1
                continue

            # Score the URL if a scorer is provided
            score = self.url_scorer.score(base_url) if self.url_scorer else 0
            
            # Skip URLs with scores below the threshold
            if score < self.score_threshold:
                self.logger.debug(f"URL {url} skipped: score {score} below threshold {self.score_threshold}")
                self.stats.urls_skipped += 1
                continue

            visited.add(base_url)
            valid_links.append((base_url, score))
        
        # If we have more valid links than capacity, sort by score and take the top ones
        if len(valid_links) > remaining_capacity:
            if self.url_scorer:
                # Sort by score in descending order
                valid_links.sort(key=lambda x: x[1], reverse=True)
            # Take only as many as we have capacity for
            valid_links = valid_links[:remaining_capacity]
            self.logger.info(f"Limiting to {remaining_capacity} URLs due to max_pages limit")
            
        # Process the final selected links
        for url, score in valid_links:
            # attach the score to metadata if needed
            if score:
                result.metadata = result.metadata or {}
                result.metadata["score"] = score
            next_level.append((url, source_url))
            depths[url] = next_depth

    async def _arun_batch(
        self,
        start_url: str,
        crawler: AsyncWebCrawler,
        config: CrawlerRunConfig,
    ) -> List[CrawlResult]:
        """
        Batch (non-streaming) mode:
        Processes one BFS level at a time, then yields all the results.
        """
        # Reset cancel event for strategy reuse
        self._cancel_event = asyncio.Event()

        # Conditional state initialization for resume support
        if self._resume_state:
            visited = set(self._resume_state.get("visited", []))
            current_level = [
                (item["url"], item["parent_url"])
                for item in self._resume_state.get("pending", [])
            ]
            depths = dict(self._resume_state.get("depths", {}))
            self._pages_crawled = self._resume_state.get("pages_crawled", 0)
        else:
            # Original initialization
            visited: Set[str] = set()
            # current_level holds tuples: (url, parent_url)
            current_level: List[Tuple[str, Optional[str]]] = [(start_url, None)]
            depths: Dict[str, int] = {start_url: 0}

        results: List[CrawlResult] = []

        while current_level and not self._cancel_event.is_set():
            # Check if we've already reached max_pages before starting a new level
            if self._pages_crawled >= self.max_pages:
                self.logger.info(f"Max pages limit ({self.max_pages}) reached, stopping crawl")
                break

            # Check external cancellation callback before processing this level
            if await self._check_cancellation():
                self.logger.info("Crawl cancelled by user")
                break

            next_level: List[Tuple[str, Optional[str]]] = []
            urls = [url for url, _ in current_level]

            # Clone the config to disable deep crawling recursion and enforce batch mode.
            batch_config = config.clone(deep_crawl_strategy=None, stream=False)
            batch_results = await crawler.arun_many(urls=urls, config=batch_config)

            for result in batch_results:
                url = result.url
                depth = depths.get(url, 0)
                result.metadata = result.metadata or {}
                result.metadata["depth"] = depth
                parent_url = next((parent for (u, parent) in current_level if u == url), None)
                result.metadata["parent_url"] = parent_url
                results.append(result)

                # Only discover links from successful crawls
                if result.success:
                    # Increment pages crawled per URL for accurate state tracking
                    self._pages_crawled += 1

                    # Link discovery will handle the max pages limit internally
                    await self.link_discovery(result, url, depth, visited, next_level, depths)

                    # Capture state after EACH URL processed (if callback set)
                    if self._on_state_change:
                        state = {
                            "strategy_type": "bfs",
                            "visited": list(visited),
                            "pending": [{"url": u, "parent_url": p} for u, p in next_level],
                            "depths": depths,
                            "pages_crawled": self._pages_crawled,
                            "cancelled": self._cancel_event.is_set(),
                        }
                        self._last_state = state
                        await self._on_state_change(state)

            current_level = next_level

        # Final state update if cancelled
        if self._cancel_event.is_set() and self._on_state_change:
            state = {
                "strategy_type": "bfs",
                "visited": list(visited),
                "pending": [{"url": u, "parent_url": p} for u, p in current_level],
                "depths": depths,
                "pages_crawled": self._pages_crawled,
                "cancelled": True,
            }
            self._last_state = state
            await self._on_state_change(state)

        return results

    async def _arun_stream(
        self,
        start_url: str,
        crawler: AsyncWebCrawler,
        config: CrawlerRunConfig,
    ) -> AsyncGenerator[CrawlResult, None]:
        """
        Streaming mode:
        Processes one BFS level at a time and yields results immediately as they arrive.
        """
        # Reset cancel event for strategy reuse
        self._cancel_event = asyncio.Event()

        # Conditional state initialization for resume support
        if self._resume_state:
            visited = set(self._resume_state.get("visited", []))
            current_level = [
                (item["url"], item["parent_url"])
                for item in self._resume_state.get("pending", [])
            ]
            depths = dict(self._resume_state.get("depths", {}))
            self._pages_crawled = self._resume_state.get("pages_crawled", 0)
        else:
            # Original initialization
            visited: Set[str] = set()
            current_level: List[Tuple[str, Optional[str]]] = [(start_url, None)]
            depths: Dict[str, int] = {start_url: 0}

        while current_level and not self._cancel_event.is_set():
            # Check external cancellation callback before processing this level
            if await self._check_cancellation():
                self.logger.info("Crawl cancelled by user")
                break

            next_level: List[Tuple[str, Optional[str]]] = []
            urls = [url for url, _ in current_level]
            visited.update(urls)

            stream_config = config.clone(deep_crawl_strategy=None, stream=True)
            stream_gen = await crawler.arun_many(urls=urls, config=stream_config)
            
            # Keep track of processed results for this batch
            results_count = 0
            async for result in stream_gen:
                url = result.url
                depth = depths.get(url, 0)
                result.metadata = result.metadata or {}
                result.metadata["depth"] = depth
                parent_url = next((parent for (u, parent) in current_level if u == url), None)
                result.metadata["parent_url"] = parent_url
                
                # Count only successful crawls
                if result.success:
                    self._pages_crawled += 1
                    # Check if we've reached the limit during batch processing
                    if self._pages_crawled >= self.max_pages:
                        self.logger.info(f"Max pages limit ({self.max_pages}) reached during batch, stopping crawl")
                        break  # Exit the generator
                
                results_count += 1
                yield result
                
                # Only discover links from successful crawls
                if result.success:
                    # Link discovery will handle the max pages limit internally
                    await self.link_discovery(result, url, depth, visited, next_level, depths)

                    # Capture state after EACH URL processed (if callback set)
                    if self._on_state_change:
                        state = {
                            "strategy_type": "bfs",
                            "visited": list(visited),
                            "pending": [{"url": u, "parent_url": p} for u, p in next_level],
                            "depths": depths,
                            "pages_crawled": self._pages_crawled,
                            "cancelled": self._cancel_event.is_set(),
                        }
                        self._last_state = state
                        await self._on_state_change(state)

            # If we didn't get results back (e.g. due to errors), avoid getting stuck in an infinite loop
            # by considering these URLs as visited but not counting them toward the max_pages limit
            if results_count == 0 and urls:
                self.logger.warning(f"No results returned for {len(urls)} URLs, marking as visited")

            current_level = next_level

        # Final state update if cancelled
        if self._cancel_event.is_set() and self._on_state_change:
            state = {
                "strategy_type": "bfs",
                "visited": list(visited),
                "pending": [{"url": u, "parent_url": p} for u, p in current_level],
                "depths": depths,
                "pages_crawled": self._pages_crawled,
                "cancelled": True,
            }
            self._last_state = state
            await self._on_state_change(state)

    async def shutdown(self) -> None:
        """
        Clean up resources and signal cancellation of the crawl.
        """
        self._cancel_event.set()
        self.stats.end_time = datetime.now()

    def export_state(self) -> Optional[Dict[str, Any]]:
        """
        Export current crawl state for external persistence.

        Note: This returns the last captured state. For real-time state,
        use the on_state_change callback.

        Returns:
            Dict with strategy state, or None if no state captured yet.
        """
        return self._last_state

```


## File: crawl4ai/deep_crawling/filters.py


```py
from abc import ABC, abstractmethod
from typing import List, Pattern, Set, Union
from urllib.parse import urlparse
from array import array
import re
import logging
from functools import lru_cache
import fnmatch
from dataclasses import dataclass
import weakref
import math
from collections import defaultdict
from typing import Dict
from ..utils import HeadPeekr
import asyncio
import inspect


@dataclass
class FilterStats:
    __slots__ = ("_counters",)

    def __init__(self):
        # Use array of unsigned ints for atomic operations
        self._counters = array("I", [0, 0, 0])  # total, passed, rejected

    @property
    def total_urls(self):
        return self._counters[0]

    @property
    def passed_urls(self):
        return self._counters[1]

    @property
    def rejected_urls(self):
        return self._counters[2]


class URLFilter(ABC):
    """Optimized base filter class"""

    __slots__ = ("name", "stats", "_logger_ref")

    def __init__(self, name: str = None):
        self.name = name or self.__class__.__name__
        self.stats = FilterStats()
        # Lazy logger initialization using weakref
        self._logger_ref = None

    @property
    def logger(self):
        if self._logger_ref is None or self._logger_ref() is None:
            logger = logging.getLogger(f"urlfilter.{self.name}")
            self._logger_ref = weakref.ref(logger)
        return self._logger_ref()

    @abstractmethod
    def apply(self, url: str) -> bool:
        pass

    def _update_stats(self, passed: bool):
        # Use direct array index for speed
        self.stats._counters[0] += 1  # total
        self.stats._counters[1] += passed  # passed
        self.stats._counters[2] += not passed  # rejected


class FilterChain:
    """Optimized filter chain"""

    __slots__ = ("filters", "stats", "_logger_ref")

    def __init__(self, filters: List[URLFilter] = None):
        self.filters = tuple(filters or [])  # Immutable tuple for speed
        self.stats = FilterStats()
        self._logger_ref = None

    @property
    def logger(self):
        if self._logger_ref is None or self._logger_ref() is None:
            logger = logging.getLogger("urlfilter.chain")
            self._logger_ref = weakref.ref(logger)
        return self._logger_ref()

    def add_filter(self, filter_: URLFilter) -> "FilterChain":
        """Add a filter to the chain"""
        self.filters = self.filters + (filter_,)
        return self  # Enable method chaining

    async def apply(self, url: str) -> bool:
        """Apply all filters concurrently when possible"""
        self.stats._counters[0] += 1  # Total processed URLs

        tasks = []
        for f in self.filters:
            result = f.apply(url)

            if inspect.isawaitable(result):
                tasks.append(result)  # Collect async tasks
            elif not result:  # Sync rejection
                self.stats._counters[2] += 1  # Sync rejected
                return False

        if tasks:
            results = await asyncio.gather(*tasks)

            # Count how many filters rejected
            rejections = results.count(False)
            self.stats._counters[2] += rejections

            if not all(results):
                return False  # Stop early if any filter rejected

        self.stats._counters[1] += 1  # Passed
        return True


class URLPatternFilter(URLFilter):
    """Pattern filter balancing speed and completeness"""

    __slots__ = (
        "patterns",  # Store original patterns for serialization
        "use_glob",  # Store original use_glob for serialization  
        "reverse",   # Store original reverse for serialization
        "_simple_suffixes",
        "_simple_prefixes",
        "_domain_patterns",
        "_path_patterns",
        "_reverse",
    )

    PATTERN_TYPES = {
        "SUFFIX": 1,  # *.html
        "PREFIX": 2,  # /foo/*
        "DOMAIN": 3,  # *.example.com
        "PATH": 4,  # Everything else
        "REGEX": 5,
    }

    def __init__(
        self,
        patterns: Union[str, Pattern, List[Union[str, Pattern]]],
        use_glob: bool = True,
        reverse: bool = False,
    ):
        super().__init__()
        # Store original constructor params for serialization
        self.patterns = patterns
        self.use_glob = use_glob
        self.reverse = reverse
        
        self._reverse = reverse
        patterns = [patterns] if isinstance(patterns, (str, Pattern)) else patterns

        self._simple_suffixes = set()
        self._simple_prefixes = set()
        self._domain_patterns = []
        self._path_patterns = []

        for pattern in patterns:
            pattern_type = self._categorize_pattern(pattern)
            self._add_pattern(pattern, pattern_type)

    def _categorize_pattern(self, pattern: str) -> int:
        """Categorize pattern for specialized handling"""
        if not isinstance(pattern, str):
            return self.PATTERN_TYPES["PATH"]

        # Check if it's a regex pattern
        if pattern.startswith("^") or pattern.endswith("$") or "\\d" in pattern:
            return self.PATTERN_TYPES["REGEX"]

        if pattern.count("*") == 1:
            if pattern.startswith("*."):
                return self.PATTERN_TYPES["SUFFIX"]
            if pattern.endswith("/*"):
                return self.PATTERN_TYPES["PREFIX"]

        if "://" in pattern and pattern.startswith("*."):
            return self.PATTERN_TYPES["DOMAIN"]

        return self.PATTERN_TYPES["PATH"]

    def _add_pattern(self, pattern: str, pattern_type: int):
        """Add pattern to appropriate matcher"""
        if pattern_type == self.PATTERN_TYPES["REGEX"]:
            # For regex patterns, compile directly without glob translation
            if isinstance(pattern, str) and (
                pattern.startswith("^") or pattern.endswith("$") or "\\d" in pattern
            ):
                self._path_patterns.append(re.compile(pattern))
                return
        elif pattern_type == self.PATTERN_TYPES["SUFFIX"]:
            self._simple_suffixes.add(pattern[2:])
        elif pattern_type == self.PATTERN_TYPES["PREFIX"]:
            self._simple_prefixes.add(pattern[:-2])
        elif pattern_type == self.PATTERN_TYPES["DOMAIN"]:
            self._domain_patterns.append(re.compile(pattern.replace("*.", r"[^/]+\.")))
        else:
            if isinstance(pattern, str):
                # Handle complex glob patterns
                if "**" in pattern:
                    pattern = pattern.replace("**", ".*")
                if "{" in pattern:
                    # Convert {a,b} to (a|b)
                    pattern = re.sub(
                        r"\{([^}]+)\}",
                        lambda m: f'({"|".join(m.group(1).split(","))})',
                        pattern,
                    )
                pattern = fnmatch.translate(pattern)
            self._path_patterns.append(
                pattern if isinstance(pattern, Pattern) else re.compile(pattern)
            )

    @lru_cache(maxsize=10000)
    def apply(self, url: str) -> bool:
        url_path = urlparse(url).path

        # Quick suffix check (*.html)
        if self._simple_suffixes:
            if url_path.split("/")[-1].split(".")[-1] in self._simple_suffixes:
                result = True
                self._update_stats(result)
                return not result if self._reverse else result

        # Domain check
        if self._domain_patterns:
            for pattern in self._domain_patterns:
                if pattern.match(url):
                    result = True
                    self._update_stats(result)
                    return not result if self._reverse else result

        # Prefix check (/foo/* or https://domain/foo/*)
        if self._simple_prefixes:
            for prefix in self._simple_prefixes:
                # Use url_path for path-only prefixes, full URL for absolute prefixes
                match_against = url if '://' in prefix else url_path
                if match_against.startswith(prefix):
                    if len(match_against) == len(prefix) or match_against[len(prefix)] in ['/', '?', '#']:
                        result = True
                        self._update_stats(result)
                        return not result if self._reverse else result

        # Complex patterns
        if self._path_patterns:
            if any(p.search(url) for p in self._path_patterns):
                result = True
                self._update_stats(result)
                return not result if self._reverse else result

        result = False
        self._update_stats(result)
        return not result if self._reverse else result


class ContentTypeFilter(URLFilter):
    """Optimized content type filter using fast lookups"""

    __slots__ = ("allowed_types", "_ext_map", "_check_extension")

    # Fast extension to mime type mapping
    _MIME_MAP = {
        # Text Formats
        "txt": "text/plain",
        "html": "text/html",
        "htm": "text/html",
        "xhtml": "application/xhtml+xml",
        "css": "text/css",
        "csv": "text/csv",
        "ics": "text/calendar",
        "js": "application/javascript",
        # Images
        "bmp": "image/bmp",
        "gif": "image/gif",
        "jpeg": "image/jpeg",
        "jpg": "image/jpeg",
        "png": "image/png",
        "svg": "image/svg+xml",
        "tiff": "image/tiff",
        "ico": "image/x-icon",
        "webp": "image/webp",
        # Audio
        "mp3": "audio/mpeg",
        "wav": "audio/wav",
        "ogg": "audio/ogg",
        "m4a": "audio/mp4",
        "aac": "audio/aac",
        # Video
        "mp4": "video/mp4",
        "mpeg": "video/mpeg",
        "webm": "video/webm",
        "avi": "video/x-msvideo",
        "mov": "video/quicktime",
        "flv": "video/x-flv",
        "wmv": "video/x-ms-wmv",
        "mkv": "video/x-matroska",
        # Applications
        "json": "application/json",
        "xml": "application/xml",
        "pdf": "application/pdf",
        "zip": "application/zip",
        "gz": "application/gzip",
        "tar": "application/x-tar",
        "rar": "application/vnd.rar",
        "7z": "application/x-7z-compressed",
        "exe": "application/vnd.microsoft.portable-executable",
        "msi": "application/x-msdownload",
        # Fonts
        "woff": "font/woff",
        "woff2": "font/woff2",
        "ttf": "font/ttf",
        "otf": "font/otf",
        # Microsoft Office
        "doc": "application/msword",
        "dot": "application/msword",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "xls": "application/vnd.ms-excel",
        "ppt": "application/vnd.ms-powerpoint",
        "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        # OpenDocument Formats
        "odt": "application/vnd.oasis.opendocument.text",
        "ods": "application/vnd.oasis.opendocument.spreadsheet",
        "odp": "application/vnd.oasis.opendocument.presentation",
        # Archives
        "tar.gz": "application/gzip",
        "tgz": "application/gzip",
        "bz2": "application/x-bzip2",
        # Others
        "rtf": "application/rtf",
        "apk": "application/vnd.android.package-archive",
        "epub": "application/epub+zip",
        "jar": "application/java-archive",
        "swf": "application/x-shockwave-flash",
        "midi": "audio/midi",
        "mid": "audio/midi",
        "ps": "application/postscript",
        "ai": "application/postscript",
        "eps": "application/postscript",
        # Custom or less common
        "bin": "application/octet-stream",
        "dmg": "application/x-apple-diskimage",
        "iso": "application/x-iso9660-image",
        "deb": "application/x-debian-package",
        "rpm": "application/x-rpm",
        "sqlite": "application/vnd.sqlite3",
        # Placeholder
        "unknown": "application/octet-stream",  # Fallback for unknown file types
        # php
        "php": "application/x-httpd-php",
        "php3": "application/x-httpd-php",
        "php4": "application/x-httpd-php",
        "php5": "application/x-httpd-php",
        "php7": "application/x-httpd-php",
        "phtml": "application/x-httpd-php",
        "phps": "application/x-httpd-php-source",

    }

    @staticmethod
    @lru_cache(maxsize=1000)
    def _extract_extension(url: str) -> str:
        """Extracts file extension from a URL."""
        # Remove scheme (http://, https://) if present
        if "://" in url:
            url = url.split("://", 1)[-1]  # Get everything after '://'

        # Remove domain (everything up to the first '/')
        path_start = url.find("/")
        path = url[path_start:] if path_start != -1 else ""

        # Extract last filename in path
        filename = path.rsplit("/", 1)[-1] if "/" in path else ""

        # Extract and validate extension
        if "." not in filename:
            return ""

        return filename.rpartition(".")[-1].lower()

    def __init__(
        self,
        allowed_types: Union[str, List[str]],
        check_extension: bool = True,
        ext_map: Dict[str, str] = _MIME_MAP,
    ):
        super().__init__()
        # Normalize and store as frozenset for fast lookup
        self.allowed_types = frozenset(
            t.lower()
            for t in (
                allowed_types if isinstance(allowed_types, list) else [allowed_types]
            )
        )
        self._check_extension = check_extension

        # Pre-compute extension map for allowed types
        self._ext_map = frozenset(
            ext
            for ext, mime in self._MIME_MAP.items()
            if any(allowed in mime for allowed in self.allowed_types)
        )

    @lru_cache(maxsize=1000)
    def _check_url_cached(self, url: str) -> bool:
        """Cached URL checking"""
        if not self._check_extension:
            return True
        ext = self._extract_extension(url)
        if not ext:
            return True

        return ext in self._ext_map

    def apply(self, url: str) -> bool:
        """Fast extension check with caching"""
        result = self._check_url_cached(url)
        self._update_stats(result)
        return result


class DomainFilter(URLFilter):
    """Optimized domain filter with fast lookups and caching"""

    __slots__ = ("_allowed_domains", "_blocked_domains", "_domain_cache")

    # Regex for fast domain extraction
    _DOMAIN_REGEX = re.compile(r"://([^/]+)")

    def __init__(
        self,
        allowed_domains: Union[str, List[str]] = None,
        blocked_domains: Union[str, List[str]] = None,
    ):
        super().__init__()

        # Convert inputs to frozensets for immutable, fast lookups
        self._allowed_domains = (
            frozenset(self._normalize_domains(allowed_domains))
            if allowed_domains
            else None
        )
        self._blocked_domains = (
            frozenset(self._normalize_domains(blocked_domains))
            if blocked_domains
            else frozenset()
        )

    @staticmethod
    def _normalize_domains(domains: Union[str, List[str]]) -> Set[str]:
        """Fast domain normalization"""
        if isinstance(domains, str):
            return {domains.lower()}
        return {d.lower() for d in domains}
    
    @staticmethod
    def _is_subdomain(domain: str, parent_domain: str) -> bool:
        """Check if domain is a subdomain of parent_domain"""
        return domain == parent_domain or domain.endswith(f".{parent_domain}")

    @staticmethod
    @lru_cache(maxsize=10000)
    def _extract_domain(url: str) -> str:
        """Ultra-fast domain extraction with regex and caching"""
        match = DomainFilter._DOMAIN_REGEX.search(url)
        return match.group(1).lower() if match else ""

    def apply(self, url: str) -> bool:
        """Optimized domain checking with early returns"""
        # Skip processing if no filters
        if not self._blocked_domains and self._allowed_domains is None:
            self._update_stats(True)
            return True

        domain = self._extract_domain(url)

        # Check for blocked domains, including subdomains
        for blocked in self._blocked_domains:
            if self._is_subdomain(domain, blocked):
                self._update_stats(False)
                return False

        # If no allowed domains specified, accept all non-blocked
        if self._allowed_domains is None:
            self._update_stats(True)
            return True

        # Check if domain matches any allowed domain (including subdomains)
        for allowed in self._allowed_domains:
            if self._is_subdomain(domain, allowed):
                self._update_stats(True)
                return True

        # No matches found
        self._update_stats(False)
        return False


class ContentRelevanceFilter(URLFilter):
    """BM25-based relevance filter using head section content"""

    __slots__ = ("query_terms", "threshold", "k1", "b", "avgdl", "query")

    def __init__(
        self,
        query: Union[str, List[str]],
        threshold: float,
        k1: float = 1.2,
        b: float = 0.75,
        avgdl: int = 1000,
    ):
        super().__init__(name="BM25RelevanceFilter")
        if isinstance(query, list):
            self.query = " ".join(query)
        else:
            self.query = query
        self.query_terms = self._tokenize(self.query)
        self.threshold = threshold
        self.k1 = k1  # TF saturation parameter
        self.b = b  # Length normalization parameter
        self.avgdl = avgdl  # Average document length (empirical value)

    async def apply(self, url: str) -> bool:
        head_content = await HeadPeekr.peek_html(url)
        if not head_content:
            self._update_stats(False)
            return False

        # Field extraction with weighting
        fields = {
            "title": HeadPeekr.get_title(head_content) or "",
            "meta": HeadPeekr.extract_meta_tags(head_content),
        }
        doc_text = self._build_document(fields)

        score = self._bm25(doc_text)
        decision = score >= self.threshold
        self._update_stats(decision)
        return decision

    def _build_document(self, fields: Dict) -> str:
        """Weighted document construction"""
        return " ".join(
            [
                fields["title"] * 3,  # Title weight
                fields["meta"].get("description", "") * 2,
                fields["meta"].get("keywords", ""),
                " ".join(fields["meta"].values()),
            ]
        )

    def _tokenize(self, text: str) -> List[str]:
        """Fast case-insensitive tokenization"""
        return text.lower().split()

    def _bm25(self, document: str) -> float:
        """Optimized BM25 implementation for head sections"""
        doc_terms = self._tokenize(document)
        doc_len = len(doc_terms)
        tf = defaultdict(int)

        for term in doc_terms:
            tf[term] += 1

        score = 0.0
        for term in set(self.query_terms):
            term_freq = tf[term]
            idf = math.log((1 + 1) / (term_freq + 0.5) + 1)  # Simplified IDF
            numerator = term_freq * (self.k1 + 1)
            denominator = term_freq + self.k1 * (
                1 - self.b + self.b * (doc_len / self.avgdl)
            )
            score += idf * (numerator / denominator)

        return score


class SEOFilter(URLFilter):
    """Quantitative SEO quality assessment filter using head section analysis"""

    __slots__ = ("threshold", "_weights", "_kw_patterns")

    # Based on SEMrush/Google ranking factors research
    DEFAULT_WEIGHTS = {
        "title_length": 0.15,
        "title_kw": 0.18,
        "meta_description": 0.12,
        "canonical": 0.10,
        "robot_ok": 0.20,  # Most critical factor
        "schema_org": 0.10,
        "url_quality": 0.15,
    }

    def __init__(
        self,
        threshold: float = 0.65,
        keywords: List[str] = None,
        weights: Dict[str, float] = None,
    ):
        super().__init__(name="SEOFilter")
        self.threshold = threshold
        self._weights = weights or self.DEFAULT_WEIGHTS
        self._kw_patterns = (
            re.compile(
                r"\b({})\b".format("|".join(map(re.escape, keywords or []))), re.I
            )
            if keywords
            else None
        )

    async def apply(self, url: str) -> bool:
        head_content = await HeadPeekr.peek_html(url)
        if not head_content:
            self._update_stats(False)
            return False

        meta = HeadPeekr.extract_meta_tags(head_content)
        title = HeadPeekr.get_title(head_content) or ""
        parsed_url = urlparse(url)

        scores = {
            "title_length": self._score_title_length(title),
            "title_kw": self._score_keyword_presence(title),
            "meta_description": self._score_meta_description(
                meta.get("description", "")
            ),
            "canonical": self._score_canonical(meta.get("canonical"), url),
            "robot_ok": 1.0 if "noindex" not in meta.get("robots", "") else 0.0,
            "schema_org": self._score_schema_org(head_content),
            "url_quality": self._score_url_quality(parsed_url),
        }

        total_score = sum(
            weight * scores[factor] for factor, weight in self._weights.items()
        )

        decision = total_score >= self.threshold
        self._update_stats(decision)
        return decision

    def _score_title_length(self, title: str) -> float:
        length = len(title)
        if 50 <= length <= 60:
            return 1.0
        if 40 <= length < 50 or 60 < length <= 70:
            return 0.7
        return 0.3  # Poor length

    def _score_keyword_presence(self, text: str) -> float:
        if not self._kw_patterns:
            return 0.0
        matches = len(self._kw_patterns.findall(text))
        return min(matches * 0.3, 1.0)  # Max 3 matches

    def _score_meta_description(self, desc: str) -> float:
        length = len(desc)
        if 140 <= length <= 160:
            return 1.0
        return 0.5 if 120 <= length <= 200 else 0.2

    def _score_canonical(self, canonical: str, original: str) -> float:
        if not canonical:
            return 0.5  # Neutral score
        return 1.0 if canonical == original else 0.2

    def _score_schema_org(self, html: str) -> float:
        # Detect any schema.org markup in head
        return (
            1.0
            if re.search(r'<script[^>]+type=["\']application/ld\+json', html)
            else 0.0
        )

    def _score_url_quality(self, parsed_url) -> float:
        score = 1.0
        path = parsed_url.path.lower()

        # Penalty factors
        if len(path) > 80:
            score *= 0.7
        if re.search(r"\d{4}", path):
            score *= 0.8  # Numbers in path
        if parsed_url.query:
            score *= 0.6  # URL parameters
        if "_" in path:
            score *= 0.9  # Underscores vs hyphens

        return score

```


## File: crawl4ai/deep_crawling/scorers.py


```py
from abc import ABC, abstractmethod
from typing import List, Dict, Optional
from dataclasses import dataclass
from urllib.parse import urlparse, unquote
import re
import logging
from functools import lru_cache
from array import array
import ctypes
import platform
PLATFORM = platform.system()

# Pre-computed scores for common year differences
_SCORE_LOOKUP = [1.0, 0.5, 0.3333333333333333, 0.25]

# Pre-computed scores for common year differences
_FRESHNESS_SCORES = [
   1.0,    # Current year
   0.9,    # Last year
   0.8,    # 2 years ago
   0.7,    # 3 years ago
   0.6,    # 4 years ago
   0.5,    # 5 years ago
]

class ScoringStats:
    __slots__ = ('_urls_scored', '_total_score', '_min_score', '_max_score')
    
    def __init__(self):
        self._urls_scored = 0
        self._total_score = 0.0
        self._min_score = None  # Lazy initialization
        self._max_score = None
    
    def update(self, score: float) -> None:
        """Optimized update with minimal operations"""
        self._urls_scored += 1
        self._total_score += score
        
        # Lazy min/max tracking - only if actually accessed
        if self._min_score is not None:
            if score < self._min_score:
                self._min_score = score
        if self._max_score is not None:
            if score > self._max_score:
                self._max_score = score
                
    def get_average(self) -> float:
        """Direct calculation instead of property"""
        return self._total_score / self._urls_scored if self._urls_scored else 0.0
    
    def get_min(self) -> float:
        """Lazy min calculation"""
        if self._min_score is None:
            self._min_score = self._total_score / self._urls_scored if self._urls_scored else 0.0
        return self._min_score
        
    def get_max(self) -> float:
        """Lazy max calculation"""
        if self._max_score is None:
            self._max_score = self._total_score / self._urls_scored if self._urls_scored else 0.0
        return self._max_score
class URLScorer(ABC):
    __slots__ = ('_weight', '_stats')
    
    def __init__(self, weight: float = 1.0):
        # Store weight directly as float32 for memory efficiency
        self._weight = ctypes.c_float(weight).value
        self._stats = ScoringStats()
    
    @abstractmethod
    def _calculate_score(self, url: str) -> float:
        """Calculate raw score for URL."""
        pass
    
    def score(self, url: str) -> float:
        """Calculate weighted score with minimal overhead."""
        score = self._calculate_score(url) * self._weight
        self._stats.update(score)
        return score
    
    @property
    def stats(self):
        """Access to scoring statistics."""
        return self._stats
    
    @property
    def weight(self):
        return self._weight

class CompositeScorer(URLScorer):
    __slots__ = ('_scorers', '_normalize', '_weights_array', '_score_array')
    
    def __init__(self, scorers: List[URLScorer], normalize: bool = True):
        """Initialize composite scorer combining multiple scoring strategies.
        
        Optimized for:
        - Fast parallel scoring
        - Memory efficient score aggregation
        - Quick short-circuit conditions
        - Pre-allocated arrays
        
        Args:
            scorers: List of scoring strategies to combine
            normalize: Whether to normalize final score by scorer count
        """
        super().__init__(weight=1.0)
        self._scorers = scorers
        self._normalize = normalize
        
        # Pre-allocate arrays for scores and weights
        self._weights_array = array('f', [s.weight for s in scorers])
        self._score_array = array('f', [0.0] * len(scorers))

    @lru_cache(maxsize=10000)
    def _calculate_score(self, url: str) -> float:
        """Calculate combined score from all scoring strategies.
        
        Uses:
        1. Pre-allocated arrays for scores
        2. Short-circuit on zero scores
        3. Optimized normalization
        4. Vectorized operations where possible
        
        Args:
            url: URL to score
            
        Returns:
            Combined and optionally normalized score
        """
        total_score = 0.0
        scores = self._score_array
        
        # Get scores from all scorers
        for i, scorer in enumerate(self._scorers):
            # Use public score() method which applies weight
            scores[i] = scorer.score(url)
            total_score += scores[i]
            
        # Normalize if requested
        if self._normalize and self._scorers:
            count = len(self._scorers)
            return total_score / count
            
        return total_score

    def score(self, url: str) -> float:
        """Public scoring interface with stats tracking.
        
        Args:
            url: URL to score
            
        Returns:
            Final combined score
        """
        score = self._calculate_score(url)
        self.stats.update(score)
        return score

class KeywordRelevanceScorer(URLScorer):
    __slots__ = ('_weight', '_stats', '_keywords', '_case_sensitive')
    
    def __init__(self, keywords: List[str], weight: float = 1.0, case_sensitive: bool = False):
        super().__init__(weight=weight)
        self._case_sensitive = case_sensitive
        # Pre-process keywords once
        self._keywords = [k if case_sensitive else k.lower() for k in keywords]
    
    @lru_cache(maxsize=10000)
    def _url_bytes(self, url: str) -> bytes:
        """Cache decoded URL bytes"""
        return url.encode('utf-8') if self._case_sensitive else url.lower().encode('utf-8')
    
    
    def _calculate_score(self, url: str) -> float:
        """Fast string matching without regex or byte conversion"""
        if not self._case_sensitive:
            url = url.lower()
            
        matches = sum(1 for k in self._keywords if k in url)
        
        # Fast return paths
        if not matches:
            return 0.0
        if matches == len(self._keywords):
            return 1.0
            
        return matches / len(self._keywords)

class PathDepthScorer(URLScorer):
    __slots__ = ('_weight', '_stats', '_optimal_depth')  # Remove _url_cache
    
    def __init__(self, optimal_depth: int = 3, weight: float = 1.0):
        super().__init__(weight=weight)
        self._optimal_depth = optimal_depth

    @staticmethod
    @lru_cache(maxsize=10000)
    def _quick_depth(path: str) -> int:
        """Ultra fast path depth calculation.
        
        Examples:
            - "http://example.com" -> 0  # No path segments
            - "http://example.com/" -> 0  # Empty path
            - "http://example.com/a" -> 1
            - "http://example.com/a/b" -> 2
        """
        if not path or path == '/':
            return 0
            
        if '/' not in path:
            return 0
            
        depth = 0
        last_was_slash = True
        
        for c in path:
            if c == '/':
                if not last_was_slash:
                    depth += 1
                last_was_slash = True
            else:
                last_was_slash = False
                
        if not last_was_slash:
            depth += 1
            
        return depth

    @lru_cache(maxsize=10000)  # Cache the whole calculation
    def _calculate_score(self, url: str) -> float:
        pos = url.find('/', url.find('://') + 3)
        if pos == -1:
            depth = 0
        else:
            depth = self._quick_depth(url[pos:])
            
        # Use lookup table for common distances
        distance = depth - self._optimal_depth
        distance = distance if distance >= 0 else -distance  # Faster than abs()
        
        if distance < 4:
            return _SCORE_LOOKUP[distance]
            
        return 1.0 / (1.0 + distance)                                             

class ContentTypeScorer(URLScorer):
    __slots__ = ('_weight', '_exact_types', '_regex_types')

    def __init__(self, type_weights: Dict[str, float], weight: float = 1.0):
        """Initialize scorer with type weights map.
        
        Args:
            type_weights: Dict mapping file extensions/patterns to scores (e.g. {'.html$': 1.0})
            weight: Overall weight multiplier for this scorer
        """
        super().__init__(weight=weight)
        self._exact_types = {}  # Fast lookup for simple extensions
        self._regex_types = []  # Fallback for complex patterns
        
        # Split into exact vs regex matchers for performance
        for pattern, score in type_weights.items():
            if pattern.startswith('.') and pattern.endswith('$'):
                ext = pattern[1:-1]
                self._exact_types[ext] = score
            else:
                self._regex_types.append((re.compile(pattern), score))
                
        # Sort complex patterns by score for early exit
        self._regex_types.sort(key=lambda x: -x[1])

    @staticmethod
    @lru_cache(maxsize=10000)
    def _quick_extension(url: str) -> str:
        """Extract file extension ultra-fast without regex/splits.
        
        Handles:
        - Basic extensions: "example.html" -> "html"
        - Query strings: "page.php?id=1" -> "php" 
        - Fragments: "doc.pdf#page=1" -> "pdf"
        - Path params: "file.jpg;width=100" -> "jpg"
        
        Args:
            url: URL to extract extension from
            
        Returns:
            Extension without dot, or empty string if none found
        """
        pos = url.rfind('.')
        if pos == -1:
            return ''
        
        # Find first non-alphanumeric char after extension
        end = len(url)
        for i in range(pos + 1, len(url)):
            c = url[i]
            # Stop at query string, fragment, path param or any non-alphanumeric
            if c in '?#;' or not c.isalnum():
                end = i
                break
                
        return url[pos + 1:end].lower()

    @lru_cache(maxsize=10000)
    def _calculate_score(self, url: str) -> float:
        """Calculate content type score for URL.
        
        Uses staged approach:
        1. Try exact extension match (fast path)
        2. Fall back to regex patterns if needed
        
        Args:
            url: URL to score
            
        Returns:
            Score between 0.0 and 1.0 * weight
        """
        # Fast path: direct extension lookup
        ext = self._quick_extension(url)
        if ext:
            score = self._exact_types.get(ext, None)
            if score is not None:
                return score
                
        # Slow path: regex patterns
        for pattern, score in self._regex_types:
            if pattern.search(url):
                return score

        return 0.0

class FreshnessScorer(URLScorer):
    __slots__ = ('_weight', '_date_pattern', '_current_year')

    def __init__(self, weight: float = 1.0, current_year: int = 2024):
        """Initialize freshness scorer.
        
        Extracts and scores dates from URLs using format:
        - YYYY/MM/DD 
        - YYYY-MM-DD
        - YYYY_MM_DD
        - YYYY (year only)
        
        Args:
            weight: Score multiplier
            current_year: Year to calculate freshness against (default 2024)
        """
        super().__init__(weight=weight)
        self._current_year = current_year
        
        # Combined pattern for all date formats
        # Uses non-capturing groups (?:) and alternation
        self._date_pattern = re.compile(
            r'(?:/'  # Path separator
            r'|[-_])'  # or date separators
            r'((?:19|20)\d{2})'  # Year group (1900-2099)
            r'(?:'  # Optional month/day group
            r'(?:/|[-_])'  # Date separator  
            r'(?:\d{2})'  # Month
            r'(?:'  # Optional day
            r'(?:/|[-_])'  # Date separator
            r'(?:\d{2})'  # Day
            r')?'  # Day is optional
            r')?'  # Month/day group is optional
        )

    @lru_cache(maxsize=10000)
    def _extract_year(self, url: str) -> Optional[int]:
        """Extract the most recent year from URL.
        
        Args:
            url: URL to extract year from
            
        Returns:
            Year as int or None if no valid year found
        """
        matches = self._date_pattern.finditer(url)
        latest_year = None
        
        # Find most recent year
        for match in matches:
            year = int(match.group(1))
            if (year <= self._current_year and  # Sanity check
                (latest_year is None or year > latest_year)):
                latest_year = year
                
        return latest_year

    @lru_cache(maxsize=10000) 
    def _calculate_score(self, url: str) -> float:
        """Calculate freshness score based on URL date.
        
        More recent years score higher. Uses pre-computed scoring
        table for common year differences.
        
        Args:
            url: URL to score
            
        Returns:
            Score between 0.0 and 1.0 * weight
        """
        year = self._extract_year(url)
        if year is None:
            return 0.5  # Default score
            
        # Use lookup table for common year differences
        year_diff = self._current_year - year
        if year_diff < len(_FRESHNESS_SCORES):
            return _FRESHNESS_SCORES[year_diff]
            
        # Fallback calculation for older content
        return max(0.1, 1.0 - year_diff * 0.1)

class DomainAuthorityScorer(URLScorer):
    __slots__ = ('_weight', '_domain_weights', '_default_weight', '_top_domains')
    
    def __init__(
        self,
        domain_weights: Dict[str, float],
        default_weight: float = 0.5,
        weight: float = 1.0,
    ):
        """Initialize domain authority scorer.
        
        Args:
            domain_weights: Dict mapping domains to authority scores
            default_weight: Score for unknown domains
            weight: Overall scorer weight multiplier
            
        Example:
            {
                'python.org': 1.0,
                'github.com': 0.9,
                'medium.com': 0.7
            }
        """
        super().__init__(weight=weight)
        
        # Pre-process domains for faster lookup
        self._domain_weights = {
            domain.lower(): score 
            for domain, score in domain_weights.items()
        }
        self._default_weight = default_weight
        
        # Cache top domains for fast path
        self._top_domains = {
            domain: score
            for domain, score in sorted(
                domain_weights.items(), 
                key=lambda x: -x[1]
            )[:5]  # Keep top 5 highest scoring domains
        }

    @staticmethod
    @lru_cache(maxsize=10000)
    def _extract_domain(url: str) -> str:
        """Extract domain from URL ultra-fast.
        
        Handles:
        - Basic domains: "example.com"
        - Subdomains: "sub.example.com" 
        - Ports: "example.com:8080"
        - IPv4: "192.168.1.1"
        
        Args:
            url: Full URL to extract domain from
            
        Returns:
            Lowercase domain without port
        """
        # Find domain start
        start = url.find('://') 
        if start == -1:
            start = 0
        else:
            start += 3
            
        # Find domain end
        end = url.find('/', start)
        if end == -1:
            end = url.find('?', start)
            if end == -1:
                end = url.find('#', start)
                if end == -1:
                    end = len(url)
                    
        # Extract domain and remove port
        domain = url[start:end]
        port_idx = domain.rfind(':')
        if port_idx != -1:
            domain = domain[:port_idx]
            
        return domain.lower()

    @lru_cache(maxsize=10000)
    def _calculate_score(self, url: str) -> float:
        """Calculate domain authority score.
        
        Uses staged approach:
        1. Check top domains (fastest)
        2. Check full domain weights
        3. Return default weight
        
        Args:
            url: URL to score
            
        Returns:
            Authority score between 0.0 and 1.0 * weight
        """
        domain = self._extract_domain(url)
        
        # Fast path: check top domains first
        score = self._top_domains.get(domain)
        if score is not None:
            return score
            
        # Regular path: check all domains
        return self._domain_weights.get(domain, self._default_weight)
```


## File: docs/examples/deepcrawl_example.py


```py
import asyncio
import time

from crawl4ai import CrawlerRunConfig, AsyncWebCrawler, CacheMode
from crawl4ai.content_scraping_strategy import LXMLWebScrapingStrategy
from crawl4ai.deep_crawling import BFSDeepCrawlStrategy, BestFirstCrawlingStrategy
from crawl4ai.deep_crawling.filters import (
    FilterChain,
    URLPatternFilter,
    DomainFilter,
    ContentTypeFilter,
    ContentRelevanceFilter,
    SEOFilter,
)
from crawl4ai.deep_crawling.scorers import (
    KeywordRelevanceScorer,
)


# 1️⃣ Basic Deep Crawl Setup
async def basic_deep_crawl():
    """
    PART 1: Basic Deep Crawl setup - Demonstrates a simple two-level deep crawl.

    This function shows:
    - How to set up BFSDeepCrawlStrategy (Breadth-First Search)
    - Setting depth and domain parameters
    - Processing the results to show the hierarchy
    """
    print("\n===== BASIC DEEP CRAWL SETUP =====")

    # Configure a 2-level deep crawl using Breadth-First Search strategy
    # max_depth=2 means: initial page (depth 0) + 2 more levels
    # include_external=False means: only follow links within the same domain
    config = CrawlerRunConfig(
        deep_crawl_strategy=BFSDeepCrawlStrategy(max_depth=2, include_external=False),
        scraping_strategy=LXMLWebScrapingStrategy(),
        verbose=True,  # Show progress during crawling
    )

    async with AsyncWebCrawler() as crawler:
        start_time = time.perf_counter()
        results = await crawler.arun(url="https://docs.crawl4ai.com", config=config)

        # Group results by depth to visualize the crawl tree
        pages_by_depth = {}
        for result in results:
            depth = result.metadata.get("depth", 0)
            if depth not in pages_by_depth:
                pages_by_depth[depth] = []
            pages_by_depth[depth].append(result.url)

        print(f"✅ Crawled {len(results)} pages total")

        # Display crawl structure by depth
        for depth, urls in sorted(pages_by_depth.items()):
            print(f"\nDepth {depth}: {len(urls)} pages")
            # Show first 3 URLs for each depth as examples
            for url in urls[:3]:
                print(f"  → {url}")
            if len(urls) > 3:
                print(f"  ... and {len(urls) - 3} more")

        print(
            f"\n✅ Performance: {len(results)} pages in {time.perf_counter() - start_time:.2f} seconds"
        )

# 2️⃣ Stream vs. Non-Stream Execution
async def stream_vs_nonstream():
    """
    PART 2: Demonstrates the difference between stream and non-stream execution.

    Non-stream: Waits for all results before processing
    Stream: Processes results as they become available
    """
    print("\n===== STREAM VS. NON-STREAM EXECUTION =====")

    # Common configuration for both examples
    base_config = CrawlerRunConfig(
        deep_crawl_strategy=BFSDeepCrawlStrategy(max_depth=1, include_external=False),
        scraping_strategy=LXMLWebScrapingStrategy(),
        verbose=False,
    )

    async with AsyncWebCrawler() as crawler:
        # NON-STREAMING MODE
        print("\n📊 NON-STREAMING MODE:")
        print("  In this mode, all results are collected before being returned.")

        non_stream_config = base_config.clone()
        non_stream_config.stream = False

        start_time = time.perf_counter()
        results = await crawler.arun(
            url="https://docs.crawl4ai.com", config=non_stream_config
        )

        print(f"  ✅ Received all {len(results)} results at once")
        print(f"  ✅ Total duration: {time.perf_counter() - start_time:.2f} seconds")

        # STREAMING MODE
        print("\n📊 STREAMING MODE:")
        print("  In this mode, results are processed as they become available.")

        stream_config = base_config.clone()
        stream_config.stream = True

        start_time = time.perf_counter()
        result_count = 0
        first_result_time = None

        async for result in await crawler.arun(
            url="https://docs.crawl4ai.com", config=stream_config
        ):
            result_count += 1
            if result_count == 1:
                first_result_time = time.perf_counter() - start_time
                print(
                    f"  ✅ First result received after {first_result_time:.2f} seconds: {result.url}"
                )
            elif result_count % 5 == 0:  # Show every 5th result for brevity
                print(f"  → Result #{result_count}: {result.url}")

        print(f"  ✅ Total: {result_count} results")
        print(f"  ✅ First result: {first_result_time:.2f} seconds")
        print(f"  ✅ All results: {time.perf_counter() - start_time:.2f} seconds")
        print("\n🔍 Key Takeaway: Streaming allows processing results immediately")

# 3️⃣ Introduce Filters & Scorers
async def filters_and_scorers():
    """
    PART 3: Demonstrates the use of filters and scorers for more targeted crawling.

    This function progressively adds:
    1. A single URL pattern filter
    2. Multiple filters in a chain
    3. Scorers for prioritizing pages
    """
    print("\n===== FILTERS AND SCORERS =====")

    async with AsyncWebCrawler() as crawler:
        # SINGLE FILTER EXAMPLE
        print("\n📊 EXAMPLE 1: SINGLE URL PATTERN FILTER")
        print("  Only crawl pages containing 'core' in the URL")

        # Create a filter that only allows URLs with 'guide' in them
        url_filter = URLPatternFilter(patterns=["*core*"])

        config = CrawlerRunConfig(
            deep_crawl_strategy=BFSDeepCrawlStrategy(
                max_depth=1,
                include_external=False,
                filter_chain=FilterChain([url_filter]),  # Single filter
            ),
            scraping_strategy=LXMLWebScrapingStrategy(),
            cache_mode=CacheMode.BYPASS,
            verbose=True,
        )

        results = await crawler.arun(url="https://docs.crawl4ai.com", config=config)

        print(f"  ✅ Crawled {len(results)} pages matching '*core*'")
        for result in results[:3]:  # Show first 3 results
            print(f"  → {result.url}")
        if len(results) > 3:
            print(f"  ... and {len(results) - 3} more")

        # MULTIPLE FILTERS EXAMPLE
        print("\n📊 EXAMPLE 2: MULTIPLE FILTERS IN A CHAIN")
        print("  Only crawl pages that:")
        print("  1. Contain '2024' in the URL")
        print("  2. Are from 'techcrunch.com'")
        print("  3. Are of text/html or application/javascript content type")

        # Create a chain of filters
        filter_chain = FilterChain(
            [
                URLPatternFilter(patterns=["*2024*"]),
                DomainFilter(
                    allowed_domains=["techcrunch.com"],
                    blocked_domains=["guce.techcrunch.com", "oidc.techcrunch.com"],
                ),
                ContentTypeFilter(
                    allowed_types=["text/html", "application/javascript"]
                ),
            ]
        )

        config = CrawlerRunConfig(
            deep_crawl_strategy=BFSDeepCrawlStrategy(
                max_depth=1, include_external=False, filter_chain=filter_chain
            ),
            scraping_strategy=LXMLWebScrapingStrategy(),
            verbose=True,
        )

        results = await crawler.arun(url="https://techcrunch.com", config=config)

        print(f"  ✅ Crawled {len(results)} pages after applying all filters")
        for result in results[:3]:
            print(f"  → {result.url}")
        if len(results) > 3:
            print(f"  ... and {len(results) - 3} more")

        # SCORERS EXAMPLE
        print("\n📊 EXAMPLE 3: USING A KEYWORD RELEVANCE SCORER")
        print(
            "Score pages based on relevance to keywords: 'crawl', 'example', 'async', 'configuration','javascript','css'"
        )

        # Create a keyword relevance scorer
        keyword_scorer = KeywordRelevanceScorer(
            keywords=["crawl", "example", "async", "configuration","javascript","css"], weight=1
        )

        config = CrawlerRunConfig(
            deep_crawl_strategy=BestFirstCrawlingStrategy(  
                max_depth=1, include_external=False, url_scorer=keyword_scorer
            ),
            scraping_strategy=LXMLWebScrapingStrategy(),
            cache_mode=CacheMode.BYPASS,
            verbose=True,
            stream=True,
        )

        results = []
        async for result in await crawler.arun(
            url="https://docs.crawl4ai.com", config=config
        ):
            results.append(result)
            score = result.metadata.get("score")
            print(f"  → Score: {score:.2f} | {result.url}")

        print(f"  ✅ Crawler prioritized {len(results)} pages by relevance score")
        print("  🔍 Note: BestFirstCrawlingStrategy visits highest-scoring pages first")

# 4️⃣ Advanced Filters
async def advanced_filters():
    """
    PART 4: Demonstrates advanced filtering techniques for specialized crawling.

    This function covers:
    - SEO filters
    - Text relevancy filtering
    - Combining advanced filters
    """
    print("\n===== ADVANCED FILTERS =====")

    async with AsyncWebCrawler() as crawler:
        # SEO FILTER EXAMPLE
        print("\n📊 EXAMPLE 1: SEO FILTERS")
        print(
            "Quantitative SEO quality assessment filter based searching keywords in the head section"
        )

        seo_filter = SEOFilter(
            threshold=0.5, keywords=["dynamic", "interaction", "javascript"]
        )

        config = CrawlerRunConfig(
            deep_crawl_strategy=BFSDeepCrawlStrategy(
                max_depth=1, filter_chain=FilterChain([seo_filter])
            ),
            scraping_strategy=LXMLWebScrapingStrategy(),
            verbose=True,
            cache_mode=CacheMode.BYPASS,
        )

        results = await crawler.arun(url="https://docs.crawl4ai.com", config=config)

        print(f"  ✅ Found {len(results)} pages with relevant keywords")
        for result in results:
            print(f"  → {result.url}")

        # ADVANCED TEXT RELEVANCY FILTER
        print("\n📊 EXAMPLE 2: ADVANCED TEXT RELEVANCY FILTER")

        # More sophisticated content relevance filter
        relevance_filter = ContentRelevanceFilter(
            query="Interact with the web using your authentic digital identity",
            threshold=0.7,
        )

        config = CrawlerRunConfig(
            deep_crawl_strategy=BFSDeepCrawlStrategy(
                max_depth=1, filter_chain=FilterChain([relevance_filter])
            ),
            scraping_strategy=LXMLWebScrapingStrategy(),
            verbose=True,
            cache_mode=CacheMode.BYPASS,
        )

        results = await crawler.arun(url="https://docs.crawl4ai.com", config=config)

        print(f"  ✅ Found {len(results)} pages")
        for result in results:
            relevance_score = result.metadata.get("relevance_score", 0)
            print(f"  → Score: {relevance_score:.2f} | {result.url}")

# 5️⃣ Max Pages and Score Thresholds
async def max_pages_and_thresholds():
    """
    PART 5: Demonstrates using max_pages and score_threshold parameters with different strategies.
    
    This function shows:
    - How to limit the number of pages crawled
    - How to set score thresholds for more targeted crawling
    - Comparing BFS, DFS, and Best-First strategies with these parameters
    """
    print("\n===== MAX PAGES AND SCORE THRESHOLDS =====")
    
    from crawl4ai.deep_crawling import DFSDeepCrawlStrategy
    
    async with AsyncWebCrawler() as crawler:
        # Define a common keyword scorer for all examples
        keyword_scorer = KeywordRelevanceScorer(
            keywords=["browser", "crawler", "web", "automation"], 
            weight=1.0
        )
        
        # EXAMPLE 1: BFS WITH MAX PAGES
        print("\n📊 EXAMPLE 1: BFS STRATEGY WITH MAX PAGES LIMIT")
        print("  Limit the crawler to a maximum of 5 pages")
        
        bfs_config = CrawlerRunConfig(
            deep_crawl_strategy=BFSDeepCrawlStrategy(
                max_depth=2, 
                include_external=False,
                url_scorer=keyword_scorer,
                max_pages=5  # Only crawl 5 pages
            ),
            scraping_strategy=LXMLWebScrapingStrategy(),
            verbose=True,
            cache_mode=CacheMode.BYPASS,
        )
        
        results = await crawler.arun(url="https://docs.crawl4ai.com", config=bfs_config)
        
        print(f"  ✅ Crawled exactly {len(results)} pages as specified by max_pages")
        for result in results:
            depth = result.metadata.get("depth", 0)
            print(f"  → Depth: {depth} | {result.url}")
            
        # EXAMPLE 2: DFS WITH SCORE THRESHOLD
        print("\n📊 EXAMPLE 2: DFS STRATEGY WITH SCORE THRESHOLD")
        print("  Only crawl pages with a relevance score above 0.5")
        
        dfs_config = CrawlerRunConfig(
            deep_crawl_strategy=DFSDeepCrawlStrategy(
                max_depth=2,
                include_external=False, 
                url_scorer=keyword_scorer,
                score_threshold=0.7,  # Only process URLs with scores above 0.5
                max_pages=10
            ),
            scraping_strategy=LXMLWebScrapingStrategy(),
            verbose=True,
            cache_mode=CacheMode.BYPASS,
        )
        
        results = await crawler.arun(url="https://docs.crawl4ai.com", config=dfs_config)
        
        print(f"  ✅ Crawled {len(results)} pages with scores above threshold")
        for result in results:
            score = result.metadata.get("score", 0)
            depth = result.metadata.get("depth", 0)
            print(f"  → Depth: {depth} | Score: {score:.2f} | {result.url}")
            
        # EXAMPLE 3: BEST-FIRST WITH BOTH CONSTRAINTS
        print("\n📊 EXAMPLE 3: BEST-FIRST STRATEGY WITH BOTH CONSTRAINTS")
        print("  Limit to 7 pages with scores above 0.3, prioritizing highest scores")
        
        bf_config = CrawlerRunConfig(
            deep_crawl_strategy=BestFirstCrawlingStrategy(
                max_depth=2,
                include_external=False,
                url_scorer=keyword_scorer,
                max_pages=7,          # Limit to 7 pages total
            ),
            scraping_strategy=LXMLWebScrapingStrategy(),
            verbose=True,
            cache_mode=CacheMode.BYPASS,
            stream=True,
        )
        
        results = []
        async for result in await crawler.arun(url="https://docs.crawl4ai.com", config=bf_config):
            results.append(result)
            score = result.metadata.get("score", 0)
            depth = result.metadata.get("depth", 0)
            print(f"  → Depth: {depth} | Score: {score:.2f} | {result.url}")
            
        print(f"  ✅ Crawled {len(results)} high-value pages with scores above 0.3")
        if results:
            avg_score = sum(r.metadata.get('score', 0) for r in results) / len(results)
            print(f"  ✅ Average score: {avg_score:.2f}")
            print("  🔍 Note: BestFirstCrawlingStrategy visited highest-scoring pages first")

# 6️⃣ Wrap-Up and Key Takeaways
async def wrap_up():
    """
    PART 6: Wrap-Up and Key Takeaways

    Summarize the key concepts learned in this tutorial.
    """
    print("\n===== COMPLETE CRAWLER EXAMPLE =====")
    print("Combining filters, scorers, and streaming for an optimized crawl")

    # Create a sophisticated filter chain
    filter_chain = FilterChain(
        [
            DomainFilter(
                allowed_domains=["docs.crawl4ai.com"],
                blocked_domains=["old.docs.crawl4ai.com"],
            ),
            URLPatternFilter(patterns=["*core*", "*advanced*", "*blog*"]),
            ContentTypeFilter(allowed_types=["text/html"]),
        ]
    )

    # Create a composite scorer that combines multiple scoring strategies
    keyword_scorer = KeywordRelevanceScorer(
        keywords=["crawl", "example", "async", "configuration"], weight=0.7
    )
    # Set up the configuration
    config = CrawlerRunConfig(
        deep_crawl_strategy=BestFirstCrawlingStrategy(
            max_depth=1,
            include_external=False,
            filter_chain=filter_chain,
            url_scorer=keyword_scorer,
        ),
        scraping_strategy=LXMLWebScrapingStrategy(),
        stream=True,
        verbose=True,
    )

    # Execute the crawl
    results = []
    start_time = time.perf_counter()

    async with AsyncWebCrawler() as crawler:
        async for result in await crawler.arun(
            url="https://docs.crawl4ai.com", config=config
        ):
            results.append(result)
            score = result.metadata.get("score", 0)
            depth = result.metadata.get("depth", 0)
            print(f"→ Depth: {depth} | Score: {score:.2f} | {result.url}")

    duration = time.perf_counter() - start_time

    # Summarize the results
    print(f"\n✅ Crawled {len(results)} high-value pages in {duration:.2f} seconds")
    print(
        f"✅ Average score: {sum(r.metadata.get('score', 0) for r in results) / len(results):.2f}"
    )

    # Group by depth
    depth_counts = {}
    for result in results:
        depth = result.metadata.get("depth", 0)
        depth_counts[depth] = depth_counts.get(depth, 0) + 1

    print("\n📊 Pages crawled by depth:")
    for depth, count in sorted(depth_counts.items()):
        print(f"  Depth {depth}: {count} pages")


async def run_tutorial():
    """
    Executes all tutorial sections in sequence.
    """
    print("\n🚀 CRAWL4AI DEEP CRAWLING TUTORIAL 🚀")
    print("======================================")
    print("This tutorial will walk you through deep crawling techniques,")
    print("from basic to advanced, using the Crawl4AI library.")

    # Define sections - uncomment to run specific parts during development
    tutorial_sections = [
        basic_deep_crawl,
        stream_vs_nonstream,
        filters_and_scorers,
        max_pages_and_thresholds, 
        advanced_filters,
        wrap_up,
    ]

    for section in tutorial_sections:
        await section()

    print("\n🎉 TUTORIAL COMPLETE! 🎉")
    print("You now have a comprehensive understanding of deep crawling with Crawl4AI.")
    print("For more information, check out https://docs.crawl4ai.com")

# Execute the tutorial when run directly
if __name__ == "__main__":
    asyncio.run(run_tutorial())
```
