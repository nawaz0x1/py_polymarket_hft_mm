use std::collections::HashSet;
use std::io::{Read, Write};
use std::net::{TcpListener, TcpStream};
use std::sync::{Arc, Mutex};
use std::thread;

struct InMemSetDB {
    data: Arc<Mutex<HashSet<String>>>,
}

impl InMemSetDB {
    fn new() -> Self {
        InMemSetDB {
            data: Arc::new(Mutex::new(HashSet::new())),
        }
    }

    fn add(&self, item: String) -> String {
        let mut set = self.data.lock().unwrap();
        set.insert(item);
        r#"{"success":true}"#.to_string()
    }

    fn contains(&self, item: &str) -> String {
        let set = self.data.lock().unwrap();
        let exists = set.contains(item);
        format!(r#"{{"exists":{}}}"#, exists)
    }

    fn clear(&self) -> String {
        let mut set = self.data.lock().unwrap();
        set.clear();
        r#"{"success":true}"#.to_string()
    }

    fn size(&self) -> String {
        let set = self.data.lock().unwrap();
        format!(r#"{{"size":{}}}"#, set.len())
    }
}

fn parse_request(request: &str) -> Option<(String, String, Option<String>)> {
    let lines: Vec<&str> = request.split("\r\n").collect();
    if lines.is_empty() {
        return None;
    }

    let parts: Vec<&str> = lines[0].split_whitespace().collect();
    if parts.len() < 2 {
        return None;
    }

    let method = parts[0].to_string();
    let path = parts[1].to_string();

    let body = if method == "POST" {
        if let Some(idx) = request.find("\r\n\r\n") {
            Some(request[idx + 4..].to_string())
        } else {
            None
        }
    } else {
        None
    };

    Some((method, path, body))
}

fn extract_json_field(json: &str, field: &str) -> Option<String> {
    let search = format!(r#""{}":""#, field);
    if let Some(start) = json.find(&search) {
        let value_start = start + search.len();
        if let Some(end) = json[value_start..].find('"') {
            return Some(json[value_start..value_start + end].to_string());
        }
    }
    None
}

fn handle_request(
    set: &InMemSetDB,
    method: &str,
    path: &str,
    body: Option<String>,
) -> (u16, String) {
    match (method, path) {
        ("POST", "/add") => {
            if let Some(body_str) = body {
                if let Some(item) = extract_json_field(&body_str, "item") {
                    let response = set.add(item);
                    return (200, response);
                }
                return (400, r#"{"error":"Missing item"}"#.to_string());
            }
            (400, r#"{"error":"Missing body"}"#.to_string())
        }
        ("POST", "/contains") => {
            if let Some(body_str) = body {
                if let Some(item) = extract_json_field(&body_str, "item") {
                    let response = set.contains(&item);
                    return (200, response);
                }
                return (400, r#"{"error":"Missing item"}"#.to_string());
            }
            (400, r#"{"error":"Missing body"}"#.to_string())
        }
        ("POST", "/clear") => {
            let response = set.clear();
            (200, response)
        }
        ("GET", "/size") => {
            let response = set.size();
            (200, response)
        }
        _ => (404, r#"{"error":"Not found"}"#.to_string()),
    }
}

fn build_response(status: u16, body: String) -> String {
    let status_text = match status {
        200 => "OK",
        400 => "Bad Request",
        404 => "Not Found",
        _ => "Unknown",
    };

    format!(
        "HTTP/1.1 {} {}\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{}",
        status, status_text, body.len(), body
    )
}

fn handle_client(mut stream: TcpStream, set: InMemSetDB) {
    let mut buffer = [0; 4096];

    match stream.read(&mut buffer) {
        Ok(size) => {
            if size == 0 {
                return;
            }

            let request = String::from_utf8_lossy(&buffer[..size]);

            if let Some((method, path, body)) = parse_request(&request) {
                let (status, response_body) = handle_request(&set, &method, &path, body);
                let response = build_response(status, response_body);

                let _ = stream.write_all(response.as_bytes());
                let _ = stream.flush();
            }
        }
        Err(e) => eprintln!("Error reading from stream: {}", e),
    }
}

fn main() {
    let listener = TcpListener::bind("127.0.0.1:8080").expect("Failed to bind");
    let set = InMemSetDB::new();

    println!("InMemSetDB started on http://127.0.0.1:8080");
    println!("\nEndpoints:");
    println!(r#"  POST /add       - {{"item": "value"}}"#);
    println!(r#"  POST /contains  - {{"item": "value"}}"#);
    println!("  POST /clear");
    println!("  GET  /size");
    println!("\nWaiting for connections...\n");

    for stream in listener.incoming() {
        match stream {
            Ok(stream) => {
                let set_clone = InMemSetDB {
                    data: Arc::clone(&set.data),
                };

                thread::spawn(move || {
                    handle_client(stream, set_clone);
                });
            }
            Err(e) => eprintln!("Connection failed: {}", e),
        }
    }
}
