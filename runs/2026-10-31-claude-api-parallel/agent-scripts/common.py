import dataikuapi, json
KEY = open("/home/user/migration-workspace-b/.dss_api_key").read().strip()
client = dataikuapi.DSSClient("http://localhost:11000", KEY)
PK = "GLP1_MEDICAID_B"
def proj(): return client.get_project(PK)
def pj(x): print(json.dumps(x, indent=1, default=str))

def drop_recipe(p, rname, outputs=()):
    if rname in [r["name"] for r in p.list_recipes()]:
        p.get_recipe(rname).delete()
    existing = [d["name"] for d in p.list_datasets()]
    for o in outputs:
        if o in existing:
            p.get_dataset(o).delete(drop_data=True)

def new_recipe(p, rtype, rname, inputs, output, extra_outputs=()):
    drop_recipe(p, rname, [output, *extra_outputs])
    b = p.new_recipe(rtype, rname)
    for i in inputs: b.with_input(i)
    b.with_new_output(output, "filesystem_managed", format_option_id="CSV")
    return b.create()
