============================================================
RESEARCH REPORT
============================================================
Task ID: cc-ebd95ea948ac4560
Total steps: 14
Citations: 26
Execution time: 67.84s
Provider note: Claude Code subscription (claude-sonnet-5-5, claude-haiku-5-5); web searches: 0

I've finished the searches and am writing up the report now. The evidence is thinner than I'd like on a few points, and I've marked those in the text.

# Boilerplate for modern iOS and macOS projects (as of Nov 2026)

## Summary

- **Toolchain floor:** Since April 28, 2026, App Store Connect uploads must be built with Xcode 26 or later and the iOS 26 family of SDKs ([Apple](https://www.developer.apple.com/news/upcoming-requirements/)). Xcode 27 betas have been out since June 8, 2026 ([BusinessWire](https://www.businesswire.com/news/home/20260608093428/en/)).
- **Recommended default:** One Xcode project with a thin app target per platform, and almost all code in local Swift packages. It uses SwiftUI, `@Observable`, Swift Testing, and Swift concurrency with main-actor default isolation.
- **Project generation (Tuist or XcodeGen):** Optional. Add one only when the module graph or team size makes `.pbxproj` merge conflicts or build times painful.
- **Persistence:** SwiftData for new, private-sync, iOS 17+ apps. Core Data with `NSPersistentCloudKitContainer` if you need shared or public CloudKit databases.
- **Not verified:** I couldn't confirm the Xcode 27 template changes, Swift 6.4 details, or a minimum deployment target for iOS 27.

## 1. Toolchain and platform facts

| Item | Finding | Confidence |
|---|---|---|
| App Store SDK rule | Xcode 26+ with iOS/iPadOS/tvOS/visionOS/watchOS 26 SDKs required since 2026-04-28; no later SDK deadline listed | High (Apple page) |
| Minimum OS target rule | From 2026-09-09, iOS/iPadOS uploads must target iOS 13 or later | High (Apple page, one fetch) |
| Xcode 27 | Betas since 2026-06-08; redesigned toolbar and project-creation flow, agent integration (Claude, Gemini, ChatGPT), DeviceHub | Medium (news coverage, not Apple release notes) |
| Swift 6.4 / iOS 27 deployment target | Not found | None |

Sources: [Apple upcoming requirements](https://www.developer.apple.com/news/upcoming-requirements/), [InfoQ on Xcode 27](https://infoq.com/news/2026/06/xcode-27-agents-device-hub), [iPhone in Canada](https://www.iphoneincanada.ca/2026/06/08/apple-just-unveiled-xcode-27-with-chatgpt-claude-and-gemini-built-in/).

Because the iOS 13 rule is a floor, it doesn't constrain you much. Pick your own deployment target from your audience. iOS 17 is the practical minimum if you want `@Observable` and SwiftData.

## 2. Concurrency settings in a fresh project

This is the setting most likely to surprise you with new template defaults.

- Xcode 26 new projects set **Default Actor Isolation** to `MainActor`. Existing projects stay `nonisolated`. Donny Wals says this "essentially makes your apps single-threaded by default" and that you must mark code `nonisolated` where you want concurrency ([Donny Wals](https://www.donnywals.com/setting-default-actor-isolation-in-xcode-26/)).
- Sources disagree on the Swift language mode. One forum report says a new macOS SwiftUI project in Xcode 26.1 shipped with Swift 5 mode and Minimal checking, alongside Approachable Concurrency and MainActor isolation ([Swift Forums](https://forums.swift.org/t/what-should-the-concurrency-settings-be-for-a-brand-new-project/83109)). Strict checking may therefore need switching on by hand.
- Local packages don't inherit the app target's settings. Set them per target in `Package.swift`. See [Use Your Loaf on Approachable Concurrency in packages](https://useyourloaf.com/blog/approachable-concurrency-in-swift-packages/).
- Fat Bobman covers problems that default isolation can cause: [Default Actor Isolation: New Problems from Good Intentions](https://fatbobman.com/en/posts/default-actor-isolation/).

**Recommendation:** Use main-actor default isolation for UI-facing app and feature targets. Leave networking, persistence and parsing packages `nonisolated`, with explicit actors where needed. Set the Swift language mode explicitly instead of trusting the template.

## 3. Project structure

Apple's guidance is to organize code into local packages, starting with obvious candidates such as networking ([Apple docs](https://developer.apple.com/documentation/xcode/organizing-your-code-with-local-packages.md)). The layout that came up most in the sources:

```
MyApp/
├─ MyApp.xcodeproj            # thin: iOS target + macOS target (or one multiplatform target)
├─ App/                       # @main, scenes, DI composition root, assets, entitlements
├─ Config/                    # Base/Debug/Release .xcconfig (my suggestion; sources didn't cover it)
├─ Packages/
│  ├─ Core/                   # models, utilities, logging (nonisolated)
│  ├─ Networking/             # API client
│  ├─ Persistence/            # SwiftData or Core Data stack
│  ├─ DesignSystem/           # shared SwiftUI components
│  └─ Features/               # one library per feature
└─ Tests/ (UI tests)
```

Related guidance: [Nimble on SwiftUI plus SPM modularization](https://nimblehq.co/blog/modern-approach-modularize-ios-swiftui-spm), [Dashlane on organizing packages](https://blog.dashlane.com/organize-swift-packages/), and [Cocoa with Love on module-separated layers](https://cocoawithlove.com/blog/app-submodules.html).

**Cross-platform caveats:**
- One write-up notes that macOS and iOS differ in SwiftUI behavior, especially sheets and environment propagation, so test shared components on both ([techconcepts](https://techconcepts.org/blog/shared-swift-package-architecture)).
- A suggested `Package.swift` improvement is to use enums instead of strings for target and dependency names ([DEV](https://dev.to/paliarmo/stop-using-strings-in-packageswift-a-type-safe-modular-architecture-for-ios-2h16)).
- My search found nothing on sharing xcconfig build settings across iOS and macOS targets. I included `Config/` as a common practice, not a sourced claim.

## 4. Project generation: Tuist vs XcodeGen vs plain SPM

| Option | Config | Strengths | Weaknesses |
|---|---|---|---|
| Plain Xcode project plus local SPM packages | `Package.swift` | No extra tooling, Apple-supported | A 2023 Asana post reported repetitive `Package.swift` files that couldn't share code ([Asana](https://asana.com/inside-asana/scaling-a-mature-ios-codebase-with-tuist)) |
| XcodeGen | YAML or JSON | Simple and light | String-based build settings are harder to validate ([comparison](https://prog.world/compare-xcodegen-and-tuist/?amp)) |
| Tuist | Swift manifests (`Project.swift`, `Workspace.swift`) | Similar to SPM; covers project structure, not only dependencies ([Tuist docs](https://tuist.dev/en/docs/guides/develop/projects)) | More to learn |

- The comparisons I found are mostly 2021 to 2025. Claims that Tuist scales better to large module graphs and offers build caching come from secondary sources. My fetch of Tuist's docs page did not confirm caching.
- A 2026 case study shows a hybrid approach: Wealthfront uses XcodeGen with core infrastructure in local SPM packages ([Wealthfront](https://eng.wealthfront.com/2026/03/02/xcodegen-and-the-quest-to-modularize-the-wealthfront-ios-app/)).

**Recommendation:** Start with plain Xcode plus local packages. Adopt a generator when you feel merge-conflict or scaling pain.

## 5. Data layer

| Need | Choice |
|---|---|
| New app, iOS 17+, private CloudKit sync | SwiftData |
| iOS 16 support, shared or public CloudKit databases, mature migrations | Core Data with `NSPersistentCloudKitContainer` |

Sources for the table: [3nsofts](https://3nsofts-site.pages.dev/insights/swiftdata-vs-core-data-production-ios-2026), [NativeFirst](https://nativefirst.pages.dev/blog/swiftdata-migration-back-to-core-data-2026).

- The "private database only" limit for SwiftData comes from one May 2026 guide that refers to an "iOS 19 beta". That is an odd version name, so verify it against current Apple docs.
- Apple Developer Forums have several reports of SwiftData-CloudKit sync stalling, including [stopped syncing](https://developer.apple.com/forums/thread/798951) and [large initial hydration](https://developer.apple.com/forums/thread/817386). They are anecdotal. A commonly cited fix is `initializeCloudKitSchema` ([Fat Bobman](https://fatbobman.com/en/snippet/resolving-incomplete-icloud-data-sync-in-ios-development-using-initializecloudkitschema/)).
- Use in-memory containers (`ModelConfiguration(isStoredInMemoryOnly: true)`) in tests.

## 6. Testing

- Xcode 26 runs Swift Testing and XCTest side by side in one test target, so you can migrate gradually ([Swift Testing vs XCTest, 2026](https://theswiftk.it.com/blog/swift-testing-vs-xctest-migration-guide-2026)).
- UI tests (`XCUIApplication`) remain XCTest-only ([Blake Crosley](https://blakecrosley.com/blog/swift-testing-vs-xctest)).
- Swift Testing runs in parallel by default. One community report says this can crash SwiftData tests that create multiple containers at once. That is a single report, so treat it as a caution only.
- WWDC 2026 has a testing session at [developer.apple.com/videos/play/wwdc2026/267](https://developer.apple.com/videos/play/wwdc2026/267). I didn't read its content.

## 7. Boilerplate checklist

1. Create an iOS and macOS project in Xcode 26 or later, then set the deployment targets (for example iOS 17, macOS 14).
2. Set the Swift language mode and concurrency settings explicitly (section 2).
3. Move logic into local packages. Keep the app target as the composition root.
4. Put `@Observable` models in feature packages, injected through the SwiftUI environment.
5. Pick the persistence layer (section 5) and set up CloudKit capabilities and entitlements early.
6. Use Swift Testing for unit tests and XCTest for UI tests, with CI building on Xcode 26 or later.
7. Add SwiftLint or SwiftFormat if you want. I had no sources on these, so that's my own suggestion.

## Gaps

- **Not found:** `@Observable` versus TCA/MVVM evidence, Xcode 27 template changes, Swift 6.4, the iOS 27 deployment floor, and Tuist/XcodeGen performance numbers.
- **Source quality:** Several sources are blogs or skill-aggregator pages, not Apple documentation. I flagged these where they carry claims.
- **Chart-ready data:** This research produced no quantitative benchmarks, such as build times or adoption percentages, so there's nothing to chart. The tables above are the closest fit.

## Sources

- [Apple: SDK minimum requirements](https://www.developer.apple.com/news/upcoming-requirements/)
- [Apple: Organizing your code with local packages](https://developer.apple.com/documentation/xcode/organizing-your-code-with-local-packages.md)
- [Apple WWDC26 session 267](https://developer.apple.com/videos/play/wwdc2026/267)
- [BusinessWire: WWDC26 announcement](https://www.businesswire.com/news/home/20260608093428/en/)
- [InfoQ: Xcode 27 agents and DeviceHub](https://infoq.com/news/2026/06/xcode-27-agents-device-hub)
- [iPhone in Canada: Xcode 27](https://www.iphoneincanada.ca/2026/06/08/apple-just-unveiled-xcode-27-with-chatgpt-claude-and-gemini-built-in/)
- [Donny Wals: Default actor isolation in Xcode 26](https://www.donnywals.com/setting-default-actor-isolation-in-xcode-26/)
- [Swift Forums: concurrency settings for a new project](https://forums.swift.org/t/what-should-the-concurrency-settings-be-for-a-brand-new-project/83109)
- [Use Your Loaf: Approachable Concurrency in packages](https://useyourloaf.com/blog/approachable-concurrency-in-swift-packages/)
- [Fat Bobman: Default Actor Isolation](https://fatbobman.com/en/posts/default-actor-isolation/)
- [Fat Bobman: initializeCloudKitSchema](https://fatbobman.com/en/snippet/resolving-incomplete-icloud-data-sync-in-ios-development-using-initializecloudkitschema/)
- [Tuist docs: Projects](https://tuist.dev/en/docs/guides/develop/projects)
- [Asana: Scaling a mature iOS codebase with Tuist](https://asana.com/inside-asana/scaling-a-mature-ios-codebase-with-tuist)
- [Wealthfront: XcodeGen modularization](https://eng.wealthfront.com/2026/03/02/xcodegen-and-the-quest-to-modularize-the-wealthfront-ios-app/)
- [prog.world: XcodeGen vs Tuist](https://prog.world/compare-xcodegen-and-tuist/?amp)
- [Nimble: SwiftUI plus SPM modularization](https://nimblehq.co/blog/modern-approach-modularize-ios-swiftui-spm)
- [Dashlane: Organize Swift packages](https://blog.dashlane.com/organize-swift-packages/)
- [Cocoa with Love: module-separated layers](https://cocoawithlove.com/blog/app-submodules.html)
- [techconcepts: shared Swift package architecture](https://techconcepts.org/blog/shared-swift-package-architecture)
- [DEV: type-safe Package.swift](https://dev.to/paliarmo/stop-using-strings-in-packageswift-a-type-safe-modular-architecture-for-ios-2h16)
- [3nsofts: SwiftData vs Core Data 2026](https://3nsofts-site.pages.dev/insights/swiftdata-vs-core-data-production-ios-2026)
- [NativeFirst: SwiftData back to Core Data](https://nativefirst.pages.dev/blog/swiftdata-migration-back-to-core-data-2026)
- [Apple Forums: SwiftData CloudKit stopped syncing](https://developer.apple.com/forums/thread/798951)
- [Apple Forums: CloudKit hydration stall](https://developer.apple.com/forums/thread/817386)
- [Swift Testing vs XCTest migration guide 2026](https://theswiftk.it.com/blog/swift-testing-vs-xctest-migration-guide-2026)
- [Blake Crosley: Swift Testing vs XCTest](https://blakecrosley.com/blog/swift-testing-vs-xctest)

============================================================
CITATIONS
============================================================
1. [Apple](https://www.developer.apple.com/news/upcoming-requirements/)
2. [BusinessWire](https://www.businesswire.com/news/home/20260608093428/en/)
3. [InfoQ on Xcode 27](https://infoq.com/news/2026/06/xcode-27-agents-device-hub)
4. [iPhone in Canada](https://www.iphoneincanada.ca/2026/06/08/apple-just-unveiled-xcode-27-with-chatgpt-claude-and-gemini-built-in/)
5. [Donny Wals](https://www.donnywals.com/setting-default-actor-isolation-in-xcode-26/)
6. [Swift Forums](https://forums.swift.org/t/what-should-the-concurrency-settings-be-for-a-brand-new-project/83109)
7. [Use Your Loaf on Approachable Concurrency in packages](https://useyourloaf.com/blog/approachable-concurrency-in-swift-packages/)
8. [Default Actor Isolation: New Problems from Good Intentions](https://fatbobman.com/en/posts/default-actor-isolation/)
9. [Apple docs](https://developer.apple.com/documentation/xcode/organizing-your-code-with-local-packages.md)
10. [Nimble on SwiftUI plus SPM modularization](https://nimblehq.co/blog/modern-approach-modularize-ios-swiftui-spm)
11. [Dashlane on organizing packages](https://blog.dashlane.com/organize-swift-packages/)
12. [Cocoa with Love on module-separated layers](https://cocoawithlove.com/blog/app-submodules.html)
13. [techconcepts](https://techconcepts.org/blog/shared-swift-package-architecture)
14. [DEV](https://dev.to/paliarmo/stop-using-strings-in-packageswift-a-type-safe-modular-architecture-for-ios-2h16)
15. [Asana](https://asana.com/inside-asana/scaling-a-mature-ios-codebase-with-tuist)
16. [comparison](https://prog.world/compare-xcodegen-and-tuist/?amp)
17. [Tuist docs](https://tuist.dev/en/docs/guides/develop/projects)
18. [Wealthfront](https://eng.wealthfront.com/2026/03/02/xcodegen-and-the-quest-to-modularize-the-wealthfront-ios-app/)
19. [3nsofts](https://3nsofts-site.pages.dev/insights/swiftdata-vs-core-data-production-ios-2026)
20. [NativeFirst](https://nativefirst.pages.dev/blog/swiftdata-migration-back-to-core-data-2026)
21. [stopped syncing](https://developer.apple.com/forums/thread/798951)
22. [large initial hydration](https://developer.apple.com/forums/thread/817386)
23. [Fat Bobman](https://fatbobman.com/en/snippet/resolving-incomplete-icloud-data-sync-in-ios-development-using-initializecloudkitschema/)
24. [Swift Testing vs XCTest, 2026](https://theswiftk.it.com/blog/swift-testing-vs-xctest-migration-guide-2026)
25. [Blake Crosley](https://blakecrosley.com/blog/swift-testing-vs-xctest)
26. [developer.apple.com/videos/play/wwdc2026/267](https://developer.apple.com/videos/play/wwdc2026/267)