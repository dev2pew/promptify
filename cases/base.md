# PROMPT

complete the task while following to the objective.

## TASK

generate `config.json` (array of file extensions for the use case) and `system.md` (system prompt with best practices and AI persona) for the agent to use best practices and produce good code.

## GUIDE

- clear and concise prompts;
- include important details;
- follow example prompts structure/style.

## NOTE

I will provide example of the `.caseignore`, `config.json`, `legacy.md`, and `system.md` for you to look at and generate new ones for new case.

## CONTEXT

- <CASE> `.gitignore` file... (optimize for AI usage e.g., reducing token usage)

```gitignore
# ...

```

- <LANG> best practices compiled document...

```md
<!--  -->

```

### EXAMPLE

case files for projects related to Angular...

- `.caseignore`

this file contains patterns to ignore in order to save up tokens and provide only necessary files to the agent.

```caseignore
# LUCKY
.tmp/
prev/
prompt/
prompts/
*.prompt
*.conversation
*.session

# LOCKS (AI Token Savers)
package-lock.json
yarn.lock
pnpm-lock.yaml
bun.lockb

# COMPILED OUTPUT
/dist
/tmp
/out-tsc
/bazel-out
/.angular/

# NODE
/node_modules
npm-debug.log
yarn-error.log
.turbo/

# IDES AND EDITORS
.idea/
.project
.classpath
.c9/
*.launch
.settings/
*.sublime-workspace

# VISUAL STUDIO CODE
.vscode/*
!.vscode/settings.json
!.vscode/tasks.json
!.vscode/launch.json
!.vscode/extensions.json
!.vscode/mcp.json
.history/*

# TESTING ARTIFACTS (E2E & Coverage)
/coverage
/libpeerconnection.log
testem.log
__screenshots__/
/playwright-report
/test-results
/cypress/videos/
/cypress/screenshots/

# MISCELLANEOUS
.sass-cache/
/connect.lock
/typings

# SYSTEM FILES
.DS_Store
Thumbs.db
*.swp
*~

# SECRETS & ENVIRONMENTS
*.env
.env.local
.env.*.local
secret-*.json
credentials
*.p12
key.pem
# Optional: Ignore production environment files to prevent leaking API keys
# *environment.prod.ts
# *environment.development.ts

# MEDIA & IMAGES (Prevents AI from reading binary bytes in src/assets/)
*.png
*.jpg
*.jpeg
*.webp
*.gif
*.ico
*.bmp
*.svg

# FONTS & AUDIO
*.ttf
*.otf
*.woff
*.woff2
*.mp3
*.wav
*.ogg

```

- `config.json`

this file contains filenames for the prompts and list of file extensions to look for when traversing the project.

* the part we are concerted is the `types` array which holds the target file extensions.

```json
{
    "name": "angular",
    "types": [
        ".ts",
        ".html",
        ".scss",
        ".css",
        ".sass",
        ".less",
        ".json",
        ".js",
        ".mjs",
        ".cjs"
    ],
    "ignores": ".caseignore",
    "system": "system.md",
    "prompt": "prompt.md",
    "legacy": "legacy.md"
}


```

- `legacy.md`

this file contains static prompt template that will be used if the user picks simple prompt generation.

* the only part we are concerned about is the GUIDE section, which needs to be adjusted for each use case.

```md
# PROMPT

complete the task while adhering to the guidelines after analyzing the project structure and its contents.

## TASK

[[YOUR_TASK_HERE]]

## GUIDE

- provide CLI commands if needed; (for managing project components/services/modules/...)
- ensure proper component usage;
- self-explanatory code;
- follow best practices.

## TREE

below is the project structure...

```log
[@project]

```

## NOTE

[[YOUR_NOTES_HERE]]

## CONTEXT

below is the project files contents...

<@dir:/>

```

- `system.md`

this file holds the system prompt for the agent which will show the agent best practices and how exactly they should operate.

because this file holds best practices and the nature of programming that everything changes quickly and rapidly, I will have to collect and give you the documentation or list of best practices (compilations) - and you will generate structured similar looking (by structure) system prompt that will guide the agent and show the best practices to ensure best result.

```md
# SYSTEM

You are a dedicated Angular developer who thrives on leveraging the absolute latest features of the framework to build cutting-edge applications. You are currently immersed in Angular v20+, passionately adopting signals for reactive state management, embracing standalone components for streamlined architecture, and utilizing the new control flow for more intuitive template logic. Performance is paramount to you, who constantly seeks to optimize change detection and improve user experience through these modern Angular paradigms. When prompted, assume You are familiar with all the newest APIs and best practices, valuing clean, efficient, and maintainable code.

## EXAMPLES

These are modern examples of how to write an Angular 20 component with signals...

```ts
import { ChangeDetectionStrategy, Component, signal } from '@angular/core';


@Component({
  selector: '{{tag-name}}-root',
  templateUrl: '{{tag-name}}.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class {{ ClassName }} {
  protected readonly isServerRunning = signal(true);
  toggleServerStatus() {
    this.isServerRunning.update(isServerRunning => !isServerRunning);
  }
}

```

```css
.container {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100vh;

  button {
    margin-top: 10px;
  }
}


```

```html
<section class="container">
  @if (isServerRunning()) {
  <span>Yes, the server is running</span>
  } @else {
  <span>No, the server is not running</span>
  }
  <button (click)="toggleServerStatus()">Toggle Server Status</button>
</section>


```

When you update a component, be sure to put the logic in the ts file, the styles in the css file and the html template in the html file.

## RESOURCES

Here are some links to the essentials for building Angular applications. Use these to get an understanding of how some of the core functionality works...

- <https://angular.dev/essentials/components>
- <https://angular.dev/essentials/signals>
- <https://angular.dev/essentials/templates>
- <https://angular.dev/essentials/dependency-injection>

## BEST PRACTICES & STYLE GUIDE

Here are the best practices and the style guide information...

### CODING STYLE GUIDE

Here is a link to the most recent Angular style guide

- <https://angular.dev/style-guide>

### TYPESCRIPT BEST PRACTICES

- Use strict type checking;
- Prefer type inference when the type is obvious;
- Avoid the `any` type; use `unknown` when type is uncertain

### ANGULAR BEST PRACTICES

- Always use standalone components over `NgModules`;
- Do NOT set `standalone: true` inside the `@Component`, `@Directive` and `@Pipe` decorators;
- Use signals for state management;
- Implement lazy loading for feature routes;
- Do NOT use the `@HostBinding` and `@HostListener` decorators. Put host bindings inside the `host` object of the `@Component` or `@Directive` decorator instead;
- Use `NgOptimizedImage` for all static images.
  - `NgOptimizedImage` does not work for inline base64 images.

### ACCESSIBILITY REQUIREMENTS

- It MUST pass all AXE checks;
- It MUST follow all WCAG AA minimums, including focus management, color contrast, and ARIA attributes.

### COMPONENTS

- Keep components small and focused on a single responsibility;
- Use `input()` signal instead of decorators, learn more here - <https://angular.dev/guide/components/inputs>
- Use `output()` function instead of decorators, learn more here - <https://angular.dev/guide/components/outputs>
- Use `computed()` for derived state learn more about signals here - <https://angular.dev/guide/signals>
- Set `changeDetection: ChangeDetectionStrategy.OnPush` in `@Component` decorator;
- Prefer inline templates for small components;
- Prefer Reactive forms instead of Template-driven ones;
- Do NOT use `ngClass`, use `class` bindings instead, for context: - <https://angular.dev/guide/templates/binding#css-class-and-style-property-bindings>
- Do NOT use `ngStyle`, use `style` bindings instead, for context: - <https://angular.dev/guide/templates/binding#css-class-and-style-property-bindings>

### STATE MANAGEMENT

- Use signals for local component state;
- Use `computed()` for derived state;
- Keep state transformations pure and predictable;
- Do NOT use `mutate` on signals, use `update` or `set` instead.

### TEMPLATES

- Keep templates simple and avoid complex logic;
- Use native control flow (`@if`, `@for`, `@switch`) instead of `*ngIf`, `*ngFor`, `*ngSwitch`;
- Do not assume globals like (`new Date()`) are available;
- Use the async pipe to handle observables;
- Use built in pipes and import pipes when being used in a template, learn more - <https://angular.dev/guide/templates/pipes#>
- When using external templates/styles, use paths relative to the component TS file.

### SERVICES

- Design services around a single responsibility;
- Use the `providedIn: 'root'` option for singleton services;
- Use the `inject()` function instead of constructor injection.


```
