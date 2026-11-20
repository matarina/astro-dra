"""Literal bracket-count diagnostics for experimental patch previews, never truth or an edit gate."""


def patch_rendering_diagnostics(proposals):
    results=[]
    for index,p in enumerate(proposals):
        before=p['anchor'];after=p['addition'];counts=[]
        for opening,closing in [('(',')'),('[',']'),('{','}'),('（','）'),('【','】')]:
            old=before.count(opening)-before.count(closing);new=after.count(opening)-after.count(closing)
            counts.append(dict(opening=opening,closing=closing,before_balance=old,after_balance=new,
                absolute_imbalance_increased=abs(new)>abs(old)))
        results.append(dict(candidate_index=index,counts=counts,
            scope='Literal counts only. Cannot decide valid scientific notation, grammar, source support, useful retention or approval. No text modified.'))
    return results
