import guts

root = guts.Root(port=9124)

db = guts.Babysteps("local/db")
root.putChild("_db", db)
root.putChild("_attach", guts.Attachments())
root.putChild('_stage', guts.Codestage())

guts.serve('stage.py', globals(), root=root)
