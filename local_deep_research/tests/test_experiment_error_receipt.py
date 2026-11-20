from scripts.experiment_error_receipt import error_receipt


def test_api_error_chain_preserves_status_but_redacts_credentials_and_endpoints():
    class UpstreamError(Exception):status_code=500
    inner=UpstreamError('Connection error at https://private.invalid/v1?token=abc; Bearer hidden-token; key=test-secret')
    outer=RuntimeError('wrapper failed');outer.__cause__=inner
    result=error_receipt(outer,{'EXAMPLE_API_KEY':'test-secret'})
    assert result['exception_chain'][1]['http_status']==500
    text=str(result)
    assert 'Connection error' in text and 'private.invalid' not in text
    assert 'hidden-token' not in text and 'test-secret' not in text
    assert 'wrapper failed' in text
