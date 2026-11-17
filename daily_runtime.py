"""Platform selection only; Linux keeps the existing Daily Python SDK."""
import sys

if sys.platform == 'win32':
    from windows_daily import CallClient, Daily, EventHandler
else:
    from daily import CallClient, Daily, EventHandler
