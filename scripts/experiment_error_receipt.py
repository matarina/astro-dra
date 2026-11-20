"""Sanitized diagnostics for isolated experiments, never application output."""
import os
import re


def error_receipt(exc, environment=None):
    environment=os.environ if environment is None else environment
    def clean(value):
        text=str(value)
        for key,secret in environment.items():
            if secret and any(part in key.upper() for part in ('KEY','TOKEN','PASSWORD','SECRET','ENDPOINT_URL')):
                text=text.replace(secret,'<redacted>')
        text=re.sub(r'https?://[^\s\"<>]+','<endpoint>',text)
        text=re.sub(r'(?i)Bearer\s+\S+','Bearer <redacted>',text)
        text=re.sub(r'sk-[A-Za-z0-9_-]{8,}','<redacted>',text)
        return text[:2000]
    rows=[];seen=set();current=exc
    while current is not None and id(current) not in seen and len(rows)<4:
        seen.add(id(current));row={'error_type':type(current).__name__,'sanitized_message':clean(current)}
        status=getattr(current,'status_code',None)
        if type(status) is int:row['http_status']=status
        rows.append(row);current=current.__cause__ or current.__context__
    return {'error_type':type(exc).__name__,'exception_chain':rows}
