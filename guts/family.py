from util import GetArgs, JsonPost, bschange, Babysteps

import glob
import os
import uuid

from twisted.web.resource import Resource

class BSFamily:
    def __init__(self, doctype):
        self.doctype = doctype

        self.dbs = {}           # uid -> db_res

        self.res = Resource()

        self.load_from_disk()
        self.attach_resources()

    def attach_resources(self):
        self.res.putChild("_info.json", GetArgs(self.get_info))
        self.res.putChild("_query.json", GetArgs(self.query))
        self.res.putChild("_infos.json", GetArgs(self.get_infos))

        self.res.putChild("_create", JsonPost(self.create))
        self.res.putChild("_update", JsonPost(self.update))
        self.res.putChild("_remove", JsonPost(self.remove))

    def next_id(self):
        uid = None
        while uid is None or (uid in self.dbs):
            uid = uuid.uuid4().get_hex()[:8]
        return uid

    def create(self, meta_doc=None):
        uid = self.next_id()
        db = self.make_db(uid)
        meta_doc["_id"] = "meta"
        
        bschange(db, {
            "type": "set",
            "id": "meta",
            "val": meta_doc
            }, sync=True)

        return self.get_info(uid)

    def update(self, meta_doc):
        # Must contain "id: "
        # ...The rest of the doc is sent to `meta.'
        id = meta_doc["id"]

        # Remove all of the crap that get_info adds
        for key in ["id", "created_time", "modified_time", "collaborators"]:
            if key in meta_doc:
                del meta_doc[key]
                
        db = self.dbs[id]

        old_meta = self.get_meta(id)
        # Remove everything that hasn't changed...
        new_meta = {}
        for key in meta_doc:
            if meta_doc[key] != old_meta.get(key):
                new_meta[key] = meta_doc[key]

        # And send a change, if there's anything left
        if len(new_meta) > 0:
            bschange(db, {
                "type": "set",
                "id": "meta",
                "val": new_meta
            })

        return {"update": new_meta}

    def remove(self, cmd):
        uid = cmd["id"]

        if not uid in self.dbs:
            print("Nothing to delete!", cmd)
            return
        
        trashdir = os.path.join("local/%s/_trash.bkp" % (self.doctype))
        try:
            os.makedirs(trashdir)
        except OSError:
            pass

        # XXX: How do I remove from Twisted?
        #self.res.removeChild(uid)
        del self.dbs[uid]

        oldpath = "local/%s/%s" % (self.doctype, uid)
        newpath = os.path.join(trashdir, uid)
        os.rename(oldpath, newpath)

        return {"remove": uid}

    def make_db(self, uid):
        # idempotent db initialization

        if uid in self.dbs:
            return self.dbs[uid]

        # Create a babysteps endpoint
        db = Babysteps(dbpath="local/%s/%s" % (self.doctype, uid))
        self.dbs[uid] = db
        self.res.putChild(uid, db)
        return db

    def load_from_disk(self):
        # Load all BSDBs
        for dbpath in glob.glob("local/%s/*[0-9a-f]" % (self.doctype)):
            self.make_db(os.path.basename(dbpath))

    def get_meta(self, uid):
        return self.get_doc(uid, "meta") or {}
    
    def get_doc(self, db_id, doc_id):
        if db_id not in self.dbs:
            return
        return self.dbs[db_id]._factory.steps.db.get(doc_id)

    def query(self, id=None, type=None, since=None, unless=None):
        db_bs = self.dbs[id]._factory.steps

        # Filter by `since'
        if since is None:
            docs = db_bs.db.values()
        else:
            since = float(since)

            log_items = [X for X in db_bs.log if X.get('date', 0) > since]
            uids = set([X['id'] for X in log_items])
            docs = [db_bs.db.get(X) for X in uids]

        # Filter by `type'
        if type is not None:
            docs = [X for X in docs if X.get('type') == type]

        # Filter by `unless'
        if unless is not None:
            # Filter docs to those without the unless field
            docs = [X for X in docs if not X.get(unless)]

        return docs
        
    def get_info(self, id):
        meta = dict(self.get_meta(id))
        log = self.dbs[id]._factory.steps.log

        if len(log) == 0:
            ctime = mtime = time.time()
        else:
            ctime = log[0]['date']
            mtime = log[-1]['date']

        for key in meta.keys():
            if key[0] == "_":
                del meta[key]

        meta.update({
            "id": id,
            "created_time": ctime,
            "modified_time": mtime,
        })

        return meta                

    def get_infos(self, **kw):
        _all = self.dbs.keys()
        return sorted(
            [self.get_info(X) for X in _all
             if ((not kw.get('since')) or float(kw['since']) < self.get_info(X)['modified_time'])],
            key=lambda x: x['created_time'], reverse=True)
