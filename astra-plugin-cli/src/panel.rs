//! The panel's submission page (contract FLOW-77), read out of `src/panel.yaml`.
//!
//! The address is data, not a literal in this file, for two reasons. C26 allows
//! the plugins service's host in exactly one place in this crate's sources, so
//! the question "does the CLI know a service address" has a one-file answer.
//! And C28 compares that one file with `spec/panel.yaml`, with every docs
//! literal of the page in seven locales, and with astra-registry's token file,
//! member by member — `url` and `query` — at the commit the header pins and at
//! the registry's head.
//!
//! What the CLI does with it is print it, and offer to open it in the author's
//! browser. The page fills in its form on a GET and submits nothing; the
//! submission is the author's own POST, in the panel, signed in to their own
//! account. So a link from here authenticates nobody and carries only a
//! repository and a tag, which is what `publish` has always sent.

use std::sync::OnceLock;

/// `spec/panel.yaml`, vendored. `panel_yaml_is_the_spec` fails until the two
/// are byte-identical.
const PANEL_SPEC: &str = include_str!("panel.yaml");

/// The page's address and its query parameter names, in order.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Page {
    pub url: String,
    pub query: Vec<String>,
}

/// The same deliberately dull hand-parse as `reserved-ids.yaml`'s: `key:
/// value`, `key:` then `  - item`, `#` comments. Anything else is skipped, and
/// the tests hold the result to the values, so a reader that finds nothing is
/// a red test rather than an empty link.
pub fn page() -> &'static Page {
    static PARSED: OnceLock<Page> = OnceLock::new();
    PARSED.get_or_init(|| parse(PANEL_SPEC))
}

fn parse(text: &str) -> Page {
    let mut out = Page { url: String::new(), query: Vec::new() };
    let mut in_query = false;
    for raw in text.lines() {
        let line = raw.trim();
        if line.is_empty() || line.starts_with('#') {
            continue;
        }
        if let Some(item) = line.strip_prefix("- ") {
            if in_query {
                out.query.push(item.trim().to_string());
            }
            continue;
        }
        let Some((key, value)) = line.split_once(':') else {
            continue;
        };
        let (key, value) = (key.trim(), value.trim());
        in_query = key == "query" && value.is_empty();
        if key == "url" {
            out.url = value.to_string();
        }
    }
    out
}

/// A query value, percent-encoded except for `/`.
///
/// FLOW-77 writes the parameter as `repo=<owner>/<name>`, and `/` is legal in a
/// query component (RFC 3986 §3.4), so it is left as the contract spells it.
/// Everything outside the unreserved set is encoded — `+` in a semver build
/// suffix above all, which a form decoder would otherwise read as a space.
fn encode_value(s: &str) -> String {
    let mut out = String::with_capacity(s.len() + 8);
    for b in s.bytes() {
        match b {
            b'A'..=b'Z' | b'a'..=b'z' | b'0'..=b'9' | b'-' | b'_' | b'.' | b'~' | b'/' => {
                out.push(b as char)
            }
            _ => out.push_str(&format!("%{b:02X}")),
        }
    }
    out
}

/// The prefilled submission page for `repo` (`owner/name`) at `tag`.
///
/// Every parameter the page declares is filled, in the page's order. A page
/// that grew a parameter this CLI has no value for is an error, not a link
/// with a hole in it — and it cannot reach an author, because
/// `the_submission_url_fills_every_declared_parameter` fails first.
pub fn submission_url(repo: &str, tag: &str) -> Result<String, String> {
    submission_url_for(page(), repo, tag)
}

fn submission_url_for(p: &Page, repo: &str, tag: &str) -> Result<String, String> {
    let mut url = p.url.clone();
    for (n, name) in p.query.iter().enumerate() {
        let value = match name.as_str() {
            "repo" => repo,
            "tag" => tag,
            other => {
                return Err(format!(
                    "src/panel.yaml declares a query parameter `{other}` this CLI has no value \
                     for; the page's parameters are `repo` and `tag` (contract FLOW-77)"
                ));
            }
        };
        url.push(if n == 0 { '?' } else { '&' });
        url.push_str(name);
        url.push('=');
        url.push_str(&encode_value(value));
    }
    Ok(url)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn panel_yaml_is_the_spec() {
        let spec = std::fs::read_to_string(
            std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../spec/panel.yaml"),
        )
        .expect("spec/panel.yaml is missing");
        assert_eq!(
            PANEL_SPEC, spec,
            "astra-plugin-cli/src/panel.yaml differs from spec/panel.yaml. The spec file is the \
             mirror of the registry's token file; copy it over."
        );
    }

    #[test]
    fn the_page_is_flow_77_member_by_member() {
        let p = page();
        assert_eq!(p.url, "https://astra.minice.ai/plugins/_/submit");
        assert_eq!(p.query, ["repo", "tag"]);
        assert!(!p.url.contains('?'), "`url` must be the address alone; parameters are `query`");
    }

    #[test]
    fn the_submission_url_fills_every_declared_parameter() {
        assert_eq!(
            submission_url("you/dice-roller", "v0.1.0").unwrap(),
            "https://astra.minice.ai/plugins/_/submit?repo=you/dice-roller&tag=v0.1.0"
        );
        assert_eq!(
            submission_url("you/x", "v1.0.0-rc.1+build 2").unwrap(),
            "https://astra.minice.ai/plugins/_/submit?repo=you/x&tag=v1.0.0-rc.1%2Bbuild%202",
        );
    }

    #[test]
    fn a_parameter_the_cli_cannot_fill_is_refused_rather_than_left_empty() {
        let p = parse("url: https://example.test/submit\nquery:\n  - repo\n  - tag\n  - account\n");
        assert_eq!(p.query, ["repo", "tag", "account"]);
        let e = submission_url_for(&p, "you/x", "v1").unwrap_err();
        assert!(e.contains("`account`"), "{e}");
    }
}
