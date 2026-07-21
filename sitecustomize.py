import httpx, anthropic
_orig = anthropic.Anthropic.__init__
def _p(self, **kwargs):
    kwargs.setdefault("http_client", httpx.Client(verify=False))
    _orig(self, **kwargs)
anthropic.Anthropic.__init__ = _p
