from pathlib import Path


def get_project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def get_nginx_config(name: str = "nginx.conf") -> str:
    return (get_project_root() / "deploy" / name).read_text(encoding="utf-8")


def test_nginx_has_spa_fallback_for_root_route():
    nginx_conf = get_nginx_config()

    assert "location / {" in nginx_conf
    assert "try_files $uri $uri/ /index.html;" in nginx_conf


def test_nginx_proxies_api_ws_and_assets_to_backend():
    nginx_conf = get_nginx_config()

    assert "location /api" in nginx_conf
    assert "location /ws" in nginx_conf
    assert "location /assets" in nginx_conf
    assert nginx_conf.count("proxy_pass http://backend:8002;") >= 3


def test_nginx_ws_block_keeps_upgrade_headers():
    nginx_conf = get_nginx_config()

    assert "location /ws" in nginx_conf
    assert "proxy_http_version 1.1;" in nginx_conf
    assert "proxy_set_header Upgrade $http_upgrade;" in nginx_conf
    assert 'proxy_set_header Connection "upgrade";' in nginx_conf


def test_cloudflare_nginx_preserves_https_and_websocket_proxy_contract():
    nginx_conf = get_nginx_config("nginx.cloudflare.conf")

    assert "map $http_x_forwarded_proto $forwarded_proto" in nginx_conf
    assert "https https;" in nginx_conf
    assert nginx_conf.count("proxy_set_header X-Forwarded-Proto $forwarded_proto;") >= 3
    assert "map $http_upgrade $connection_upgrade" in nginx_conf
    assert "proxy_set_header Upgrade $http_upgrade;" in nginx_conf
    assert "proxy_set_header Connection $connection_upgrade;" in nginx_conf
    assert "proxy_read_timeout 3600s;" in nginx_conf
    assert "proxy_buffering off;" in nginx_conf


def test_cloudflare_nginx_keeps_spa_proxy_and_security_headers():
    nginx_conf = get_nginx_config("nginx.cloudflare.conf")

    assert "try_files $uri $uri/ /index.html;" in nginx_conf
    assert nginx_conf.count("proxy_pass http://backend:8002;") >= 3
    assert "server_tokens off;" in nginx_conf
    assert 'add_header X-Content-Type-Options "nosniff" always;' in nginx_conf
    assert 'add_header X-Frame-Options "SAMEORIGIN" always;' in nginx_conf
    assert 'if ($http_x_forwarded_proto = "http") {' in nginx_conf
    assert 'return 308 https://$host$request_uri;' in nginx_conf
    assert 'add_header Strict-Transport-Security "max-age=31536000" always;' in nginx_conf
