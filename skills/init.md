---
name: init
description: Create or adopt an n8n project without overwriting existing files.
user-invocable: false
---

# Create or adopt a project

Path examples use bundled defaults. Resolve source and environment locations from [project configuration](../configuration.md); preserve user preferences and existing conventions.

Read existing user instructions and conventions first. Resolve the installed toolkit independently of the project. New projects use:

```bash
python3 <toolkit>/helpers/init.py --project <project>
```

For an existing project, add `--adopt`. Map established paths with repeatable `--path KIND=relative/path` options (for example `--path templates=workflows`). The supported kinds are config, templates, functions, function_tests, prompts, assets, cloud_functions and cloud_tests.

Setup adds a project manifest and missing scaffolding. It preserves existing instruction files, secrets, data, files and permissions. Repeating setup is safe. `--workspace` aliases `--project`; deprecated `--force` also preserves files and never deletes the project.

Each environment gets its own deployment binding and private state through `bootstrap-env.md`. Existing legacy YAML environments remain usable; migrate each explicitly with `bootstrap_env.py --migrate` after inspecting its mapping. Keep old memory/instruction files; add a pointer only if needed instead of replacing their contents.
