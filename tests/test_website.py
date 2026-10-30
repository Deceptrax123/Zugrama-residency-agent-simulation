from email.message import Message
import socket
import unittest
from unittest.mock import Mock,patch

from residency.store import AppError
from residency.website import PageText,destination,fetch_page


def address(ip):return [(socket.AF_INET,socket.SOCK_STREAM,6,'',(ip,443))]


class WebsiteTests(unittest.TestCase):
    def test_only_public_destinations_and_standard_web_protocols(self):
        for url in ('file:///etc/passwd','http://user:password@example.com','https://example.com:8080'):
            with self.assertRaises(AppError):destination(url)
        for ip in ('127.0.0.1','10.0.0.1','169.254.169.254','::1'):
            with patch('residency.website.socket.getaddrinfo',return_value=address(ip)):
                with self.assertRaises(AppError):destination('https://portfolio.example')
        with patch('residency.website.socket.getaddrinfo',return_value=address('1.1.1.1')):
            parsed,_,ip=destination('portfolio.example/projects')
        self.assertEqual(parsed.scheme,'https');self.assertEqual(ip,'1.1.1.1')

    def test_page_text_and_pinned_public_fetch_do_not_send_credentials(self):
        headers=Message();headers['Content-Type']='text/html; charset=utf-8'
        response=Mock(status=200,headers=headers)
        response.getheader.return_value='text/html; charset=utf-8'
        response.read.return_value=b'<h1>Solar Atlas</h1><script>IGNORE</script><p>I built a mapping tool.</p>'
        connection=Mock();connection.getresponse.return_value=response
        with patch('residency.website.socket.getaddrinfo',return_value=address('1.1.1.1')), \
             patch('residency.website.socket.create_connection') as connect, \
             patch('residency.website.http.client.HTTPConnection',return_value=connection):
            result=fetch_page('http://portfolio.example/projects')
        self.assertIn('Solar Atlas',result['text']);self.assertNotIn('IGNORE',result['text'])
        self.assertEqual(connect.call_args.args[0],('1.1.1.1',80))
        sent=connection.request.call_args.kwargs['headers']
        self.assertNotIn('Authorization',sent);self.assertNotIn('Cookie',sent)

    def test_redirect_to_private_address_is_refused_before_connecting(self):
        response=Mock(status=302);response.getheader.return_value='http://127.0.0.1/private'
        connection=Mock();connection.getresponse.return_value=response
        with patch('residency.website.socket.getaddrinfo',side_effect=[address('1.1.1.1'),address('127.0.0.1')]), \
             patch('residency.website.socket.create_connection') as connect, \
             patch('residency.website.http.client.HTTPConnection',return_value=connection):
            with self.assertRaises(AppError):fetch_page('http://portfolio.example')
        self.assertEqual(connect.call_count,1)
