"""Read the public webpage supplied by the host, without cookies or private-network access."""
from html.parser import HTMLParser
import http.client
import ipaddress
import socket
import ssl
from urllib.parse import urljoin,urlsplit,urlunsplit

from .store import AppError


class PageText(HTMLParser):
    def __init__(self):super().__init__();self.parts=[];self.hidden=0
    def handle_starttag(self,tag,attrs):
        if tag in ('script','style','noscript','svg'):self.hidden+=1
    def handle_endtag(self,tag):
        if tag in ('script','style','noscript','svg'):self.hidden=max(0,self.hidden-1)
    def handle_data(self,data):
        if not self.hidden:self.parts.append(data)


def destination(url):
    if not isinstance(url,str) or len(url)>2000:raise AppError('Provide a public website URL')
    if '://' not in url:url='https://'+url
    try:
        parsed=urlsplit(url.strip())
        port=parsed.port or (443 if parsed.scheme=='https' else 80)
    except ValueError:raise AppError('Invalid website URL') from None
    if (parsed.scheme not in ('https','http') or not parsed.hostname or parsed.username or parsed.password
            or port not in (80,443)):
        raise AppError('Use a public HTTP or HTTPS page without login credentials')
    try:addresses=socket.getaddrinfo(parsed.hostname,port,type=socket.SOCK_STREAM)
    except OSError:raise AppError('The website address could not be resolved',502) from None
    if not addresses or any(not ipaddress.ip_address(row[4][0]).is_global for row in addresses):
        raise AppError('Use a public website; private and local addresses cannot be fetched')
    return parsed,port,addresses[0][4][0]


def fetch_page(url):
    for _ in range(4):
        parsed,port,address=destination(url)
        try:
            # Pin the validated public address; preserve hostname verification and SNI.
            connection=http.client.HTTPConnection(parsed.hostname,port,timeout=10)
            connection.sock=socket.create_connection((address,port),timeout=10)
            if parsed.scheme=='https':
                connection.sock=ssl.create_default_context().wrap_socket(connection.sock,server_hostname=parsed.hostname)
            path=urlunsplit(('','',parsed.path or '/',parsed.query,''))
            connection.request('GET',path,headers={'User-Agent':'ResidencyCV/1.0','Accept':'text/html,text/plain','Accept-Encoding':'identity'})
            response=connection.getresponse()
            if response.status in (301,302,303,307,308):
                location=response.getheader('Location')
                if not location:raise AppError('The website returned an invalid redirect',502)
                url=urljoin(parsed.geturl(),location);continue
            if response.status!=200:raise AppError('The website could not be read (HTTP '+str(response.status)+')',502)
            kind=response.getheader('Content-Type','').split(';')[0].strip().lower()
            if kind not in ('text/html','text/plain','application/xhtml+xml'):
                raise AppError('Use a webpage URL; upload CV PDFs with the PDF button')
            raw=response.read(1_000_001)
            if len(raw)>1_000_000:raise AppError('This webpage is too large to read; use a specific project page',413)
            encoding=response.headers.get_content_charset() or 'utf-8'
            try:text=raw.decode(encoding,errors='replace')
            except LookupError:text=raw.decode('utf-8',errors='replace')
        except (OSError,http.client.HTTPException):raise AppError('The website could not be reached',502) from None
        finally:
            if 'connection' in locals():connection.close()
        if kind!='text/plain':
            parser=PageText();parser.feed(text);text=' '.join(parser.parts)
        text=' '.join(text.split())
        if not text:raise AppError('This page has no readable text. Try a specific project page')
        return {'url':parsed.geturl(),'text':text[:24000],'truncated':len(text)>24000}
    raise AppError('The website redirected too many times',502)
