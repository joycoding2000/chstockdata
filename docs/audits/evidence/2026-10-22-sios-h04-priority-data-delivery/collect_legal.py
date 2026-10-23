import json
import subprocess
from acquire import capture, ROOT

request = json.loads(subprocess.check_output(["node", str(ROOT / "cmf_public_request.cjs"), "2"]))
capture("513990-official-legal", "https://www.cmfchina.com/ws-business-server/fund/productAnn", **request)
capture("513530-official-legal", "https://www.huatai-pb.com/common-web/cms/content/getContents?categoryId=0044a86e22595e5ae063260212ac151b&pageNumber=1&pageSize=30")
