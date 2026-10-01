//! UI scaffolds use host primitives; resources are included in the CLI binary.
use anyhow::Result;
use std::{fs, path::Path};
mod assets {
    include!("ui_assets.rs");
}
pub fn generate(out: &Path, frontend: &str) -> Result<()> {
    fs::create_dir_all(out.join("ui"))?;
    if frontend == "vanilla" {
        fs::write(
            out.join("ui/index.html"),
            include_str!("../../resources/ui/vanilla.html"),
        )?;
        fs::write(
            out.join("ui/main.js"),
            include_str!("../../resources/ui/vanilla.js"),
        )?;
        return Ok(());
    }
    let root = out.join("frontend");
    fs::create_dir_all(&root)?;
    for (name, bytes) in [
        (
            "index.html",
            include_bytes!("../../resources/ui/react.html").as_slice(),
        ),
        (
            "bootstrap.js",
            include_bytes!("../../resources/ui/bootstrap.js").as_slice(),
        ),
        (
            "App.tsx",
            include_bytes!("../../resources/ui/App.tsx").as_slice(),
        ),
        (
            "build.mjs",
            include_bytes!("../../resources/ui/build.mjs").as_slice(),
        ),
        (
            "package.json",
            include_bytes!("../../resources/ui/package.json").as_slice(),
        ),
        (
            "bun.lock",
            include_bytes!("../../resources/ui/bun.lock").as_slice(),
        ),
    ] {
        fs::write(root.join(name), bytes)?;
    }
    for (name, bytes) in assets::AUTHORING {
        let file = root.join("vendor/astra-plugin-ui").join(name);
        fs::create_dir_all(file.parent().unwrap())?;
        fs::write(file, bytes)?;
    }
    // The initial served document exists before the first frontend build.
    fs::write(
        out.join("ui/index.html"),
        include_str!("../../resources/ui/react.html"),
    )?;
    fs::write(
        out.join("ui/bootstrap.js"),
        include_str!("../../resources/ui/bootstrap.js"),
    )?;
    Ok(())
}
pub fn minimum_version() -> String {
    // Generated snapshot, not a second handwritten version.
    let value: serde_json::Value =
        serde_json::from_str(include_str!("../../vendor/astra-plugin-ui/contract.json"))
            .expect("UI contract");
    value["minimumAstraVersion"]
        .as_str()
        .expect("UI version")
        .to_owned()
}
