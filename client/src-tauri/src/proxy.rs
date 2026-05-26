//! HTTP → Unix-socket reverse proxy used by the Companion app.
//!
//! Binds to 127.0.0.1:0 (kernel-chosen free port). For every HTTP request
//! from the embedded webview, opens a connection to the configured Unix
//! socket and forwards the request unchanged.
//!
//! V1 limitations: collects request/response bodies in memory before
//! forwarding (no SSE streaming). Sufficient for destructive admin ops
//! which are small JSON payloads. Streaming can be added later.

use std::path::PathBuf;

use http_body_util::{BodyExt, Full};
use hyper::body::{Bytes, Incoming};
use hyper::server::conn::http1 as server_http1;
use hyper::service::service_fn;
use hyper::{Request, Response, StatusCode};
use hyper_util::rt::TokioIo;
use hyperlocal::{UnixConnector, Uri as UnixUri};
use tokio::net::TcpListener;

#[derive(Clone)]
pub struct ProxyInfo {
    pub port: u16,
}

pub async fn start(
    uds_path: PathBuf,
) -> std::io::Result<(u16, tokio::task::JoinHandle<()>)> {
    let listener = TcpListener::bind("127.0.0.1:0").await?;
    let port = listener.local_addr()?.port();

    let handle = tokio::spawn(async move {
        loop {
            let (stream, _peer) = match listener.accept().await {
                Ok(pair) => pair,
                Err(e) => {
                    eprintln!("[proxy] accept error: {e}");
                    continue;
                }
            };
            let uds = uds_path.clone();
            tokio::spawn(async move {
                let io = TokioIo::new(stream);
                let svc = service_fn(move |req| forward(req, uds.clone()));
                if let Err(e) =
                    server_http1::Builder::new().serve_connection(io, svc).await
                {
                    eprintln!("[proxy] connection error: {e}");
                }
            });
        }
    });

    Ok((port, handle))
}

async fn forward(
    req: Request<Incoming>,
    uds_path: PathBuf,
) -> Result<Response<Full<Bytes>>, hyper::Error> {
    let path_and_query = req
        .uri()
        .path_and_query()
        .map(|p| p.as_str().to_string())
        .unwrap_or_else(|| "/".to_string());
    let target_uri: hyper::Uri = UnixUri::new(&uds_path, &path_and_query).into();

    let (parts, body) = req.into_parts();

    // The webview runs at tauri://localhost, which is not in the backend's
    // CORS whitelist. Override Origin to http://localhost (whitelisted) for
    // the upstream call so the backend's CORSMiddleware accepts the request
    // (especially preflight OPTIONS), then echo the original Origin back in
    // the response's Access-Control-Allow-Origin so the webview's CORS check
    // sees a matching value.
    let original_origin = parts
        .headers
        .get(hyper::header::ORIGIN)
        .cloned();

    let body_bytes = match body.collect().await {
        Ok(c) => c.to_bytes(),
        Err(_) => Bytes::new(),
    };

    let mut new_req_builder = Request::builder()
        .method(parts.method)
        .uri(target_uri);
    for (k, v) in parts.headers.iter() {
        if k == hyper::header::ORIGIN {
            continue;
        }
        new_req_builder = new_req_builder.header(k, v);
    }
    new_req_builder = new_req_builder.header(
        hyper::header::ORIGIN,
        hyper::header::HeaderValue::from_static("http://localhost"),
    );
    let new_req = match new_req_builder.body(Full::new(body_bytes)) {
        Ok(r) => r,
        Err(_) => {
            return Ok(Response::builder()
                .status(StatusCode::BAD_GATEWAY)
                .body(Full::new(Bytes::from_static(b"proxy: bad request")))
                .unwrap());
        }
    };

    let client = hyper_util::client::legacy::Client::builder(
        hyper_util::rt::TokioExecutor::new(),
    )
    .build::<_, Full<Bytes>>(UnixConnector);

    match client.request(new_req).await {
        Ok(resp) => {
            let (parts, body) = resp.into_parts();
            let bytes =
                body.collect().await.map(|c| c.to_bytes()).unwrap_or_default();
            let mut out = Response::builder().status(parts.status);
            for (k, v) in parts.headers.iter() {
                // Drop the upstream Allow-Origin so we can echo the webview's
                // real Origin (the backend saw our spoofed http://localhost).
                if k == hyper::header::ACCESS_CONTROL_ALLOW_ORIGIN {
                    continue;
                }
                out = out.header(k, v);
            }
            if let Some(origin) = original_origin {
                out = out.header(
                    hyper::header::ACCESS_CONTROL_ALLOW_ORIGIN,
                    origin,
                );
            }
            Ok(out.body(Full::new(bytes)).unwrap())
        }
        Err(e) => Ok(Response::builder()
            .status(StatusCode::BAD_GATEWAY)
            .body(Full::new(Bytes::from(format!(
                "proxy: UDS unreachable — is baluhost-backend-local.service running? ({e})"
            ))))
            .unwrap()),
    }
}
