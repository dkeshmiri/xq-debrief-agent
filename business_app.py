"""Optional dedicated workplace pilot: python business_app.py (port 5001)."""
import os
from werkzeug.middleware.dispatcher import DispatcherMiddleware
from workspace_host import load_workspace

workspace = load_workspace(data_root=os.getenv('XQ_BUSINESS_DATA_DIR'))
app = workspace.app
core = app.wsgi_app
app.wsgi_app = DispatcherMiddleware(core, {'/business': core})

if __name__ == '__main__':
    app.run(host='127.0.0.1', port=int(os.getenv('XQ_BUSINESS_PORT', '5001')), debug=False, use_reloader=False)
