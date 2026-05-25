//! Integration test: start a fake UDS server, run the proxy, verify forwarding.

#![cfg(unix)]

use std::path::PathBuf;

use baluhost_companion_lib::proxy;
use http_body_util::Full;
use hyper::body::Bytes;
use hyper::server::conn::http1 as server_http1;
use hyper::service::service_fn;
use hyper::{Request, Response};
use hyper_util::rt::TokioIo;
use tokio::net::UnixListener;

#[tokio::test]
async fn proxy_forwards_get_request() {
    let tmpdir = tempfile::tempdir().unwrap();
    let sock_path: PathBuf = tmpdir.path().join("test.sock");
    let listener = UnixListener::bind(&sock_path).unwrap();

    // Spawn a fake UDS HTTP server that always replies "hello from uds".
    let _server = tokio::spawn(async move {
        if let Ok((stream, _)) = listener.accept().await {
            let io = TokioIo::new(stream);
            let svc = service_fn(|_req: Request<hyper::body::Incoming>| async {
                Ok::<_, hyper::Error>(Response::new(Full::new(
                    Bytes::from_static(b"hello from uds"),
                )))
            });
            let _ = server_http1::Builder::new().serve_connection(io, svc).await;
        }
    });

    // Start the proxy
    let (port, _proxy_handle) = proxy::start(sock_path).await.unwrap();

    // Hit the proxy with a real TCP client
    let client = reqwest::Client::new();
    let resp = client
        .get(format!("http://127.0.0.1:{port}/anything"))
        .send()
        .await
        .unwrap();
    let body = resp.text().await.unwrap();
    assert_eq!(body, "hello from uds");
}
