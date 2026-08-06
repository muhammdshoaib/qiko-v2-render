const touchTargetsAssert = require("node:assert/strict");
const { existsSync: touchTargetsExistsSync, readFileSync: touchTargetsReadFileSync } = require("node:fs");
const { resolve: touchTargetsResolve } = require("node:path");
const touchTargetsTest = require("node:test");

// The primitives, not a page. An earlier attempt at this fixed the admin login page with a per-usage
// className and a test that grepped that one page, which would have left the other 18 call sites
// (signup, settings, all three chat composers, and the PUBLIC embed widget) below the minimum while
// reporting the problem solved.
// Resolved by probing rather than by counting "..", because this test runs both from the source tree
// and from the compiled output, and an off-by-one directory produced a confusing ENOENT rather than a
// useful failure.
const uiCandidates = [
  touchTargetsResolve(__dirname, "../../../packages/ui/src/index.tsx"),
  touchTargetsResolve(__dirname, "../../../../packages/ui/src/index.tsx"),
  touchTargetsResolve(__dirname, "../../../frontend/packages/ui/src/index.tsx"),
];
const uiPath = uiCandidates.find((candidate) => touchTargetsExistsSync(candidate));
touchTargetsAssert.ok(uiPath, `could not locate @qiko/ui source, tried: ${uiCandidates.join(", ")}`);
const uiSource = touchTargetsReadFileSync(uiPath, "utf8");

touchTargetsTest("the shared Input meets the 44px minimum touch target", () => {
  touchTargetsAssert.match(uiSource, /"flex h-11 w-full rounded-md border border-input/,
    "Input must be h-11 (44px), the WCAG 2.5.5 / Apple HIG minimum");
  touchTargetsAssert.doesNotMatch(uiSource, /"flex h-10 w-full rounded-md border border-input/,
    "Input must not regress to h-10 (40px)");
});

touchTargetsTest("the Button sizes used on touch surfaces meet the minimum", () => {
  const sizes = uiSource.match(/size: \{[^}]*\}/);
  touchTargetsAssert.ok(sizes, "Button size variants must be declared");
  const declared = sizes[0];

  // default and icon are the two reachable as a primary action on a phone.
  touchTargetsAssert.match(declared, /default: "h-11/, "default Button must be 44px tall");
  touchTargetsAssert.match(declared, /icon: "size-11"/, "icon Button must be 44x44");
  // lg must stay LARGER than default, otherwise the variant silently means nothing.
  touchTargetsAssert.match(declared, /lg: "h-12/, "lg must remain larger than default");
});

touchTargetsTest("an Input and an icon Button in the same row stay the same height", () => {
  // The three chat composers put them side by side in a flex row, so a mismatch is visible as a 4px
  // step. This is why the two primitives have to move together.
  const inputHeight = uiSource.match(/"flex (h-\d+) w-full rounded-md border border-input/);
  const iconSize = uiSource.match(/icon: "size-(\d+)"/);
  touchTargetsAssert.ok(inputHeight && iconSize);
  touchTargetsAssert.equal(inputHeight[1], `h-${iconSize[1]}`,
    "the icon Button and the Input must be the same height or the chat composers misalign");
});

touchTargetsTest("the compact sm variant stays compact, deliberately", () => {
  // Documented exception rather than an oversight: 30 secondary actions use it, always beside a larger
  // primary control. If this ever becomes the primary action on a mobile surface, revisit it.
  touchTargetsAssert.match(uiSource, /sm: "h-8 px-3"/);
  touchTargetsAssert.match(uiSource, /WCAG allows this where/,
    "the exception must stay documented at the source");
});

// Kept from the earlier attempt, which had this part right: the login copy is a stakeholder
// acceptance criterion, so a styling change must not quietly reword it.
const loginSourceRoot = touchTargetsExistsSync(touchTargetsResolve(__dirname, "../app"))
  ? touchTargetsResolve(__dirname, "..")
  : touchTargetsResolve(__dirname, "../..");
const loginPageSource = touchTargetsReadFileSync(
  touchTargetsResolve(loginSourceRoot, "app/login/page.tsx"),
  "utf8",
);

touchTargetsTest("the admin login preserves its exact copy", () => {
  for (const exactCopy of [
    "<CardTitle>Admin Sign In</CardTitle>",
    "<CardDescription>Use your admin credentials to continue.</CardDescription>",
    '<Label htmlFor="email">Email</Label>',
    '<Label htmlFor="password">Password</Label>',
    'placeholder="Enter password"',
    'aria-label={showPassword ? "Hide password" : "Show password"}',
    '<Label htmlFor="totp">Authenticator or backup code</Label>',
    'placeholder="Required when 2FA is enabled"',
    '{busy ? "Signing in..." : "Sign in"}',
    ">Forgot password?</Link>",
  ]) {
    touchTargetsAssert.ok(loginPageSource.includes(exactCopy),
      `login page must preserve exact copy: ${exactCopy}`);
  }
  touchTargetsAssert.match(loginPageSource, /placeholder=\{"you" \+ "@" \+ "company\.com"\}/);
  // Layout classes the primitives do not own must survive too.
  touchTargetsAssert.match(loginPageSource, /className="pr-10"/, "password input keeps room for the eye toggle");
});
