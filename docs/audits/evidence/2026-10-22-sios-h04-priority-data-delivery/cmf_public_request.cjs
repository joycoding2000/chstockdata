// Reproduce the anonymous public website's request serialization. No login state.
const fs = require('fs');
const vm = require('vm');
const crypto = require('crypto');
const path = require('path');
const root = __dirname;
const html = fs.readFileSync(path.join(root, 'sources/024-513990-product.raw'), 'utf8');
const script = html.match(/<script[^>]*>(window\.__NUXT__=[\s\S]*?)<\/script>/)[1];
const sandbox = {window: {}};
vm.runInNewContext(script, sandbox, {timeout: 1000});
const config = sandbox.window.__NUXT__.config.public;
const source = fs.readFileSync(path.join(root, 'sources/045-cmf-base-js.raw'), 'utf8');
const publicProtocolValue = source.match(/\$s\(n,"([a-f0-9]+)"\)/)[1];
const data = {startDate: '', endDate: '', productCode: '513990', pageNum: 1,
  pageSize: 50, isPreview: '0', keyword: '', selectTime: '', type: Number(process.argv[2] || 1),
  siteno: config.siteno, merchantId: config.merchantId, request_id: crypto.randomUUID()};
const key = crypto.createHash('sm3').update(publicProtocolValue).digest('hex').substring(0,16);
const cipher = crypto.createCipheriv('sm4-ecb', Buffer.from(key), null);
const encrypted = Buffer.concat([cipher.update(JSON.stringify(data)), cipher.final()]).toString('base64');
const requestId = source.match(/const Ns=\(\)=>"([a-f0-9]+)"/)[1];
const sign = crypto.createHash('sm3').update(`secret=${publicProtocolValue}data=${encrypted}request_id=${requestId}encrypted=true`).digest('hex');
process.stdout.write(JSON.stringify({headers: {'tk-trans-merchant-key': 'thinkive', 'tk-trans-signature': sign},
  params: {data: encrypted, request_id: requestId, encrypted: 'true'}}));
