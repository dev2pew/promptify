# ANDROID

Android — Build reliable, secure, adaptive apps with Kotlin, Jetpack Compose, Material 3, and modern Jetpack libraries.

## TABLE OF CONTENTS

- [Android Developers](https://developer.android.com/);
- [Guide to App Architecture](https://developer.android.com/topic/architecture);
- [Recommendations for Android Architecture](https://developer.android.com/topic/architecture/recommendations);
- [Kotlin Style Guide for Android](https://developer.android.com/kotlin/style-guide);
- [Jetpack Compose](https://developer.android.com/develop/ui/compose);
- [Compose Tutorial](https://developer.android.com/develop/ui/compose/tutorial);
- [Compose Quick Guides](https://developer.android.com/quick-guides);
- [Compose API Guidelines](https://android.googlesource.com/platform/frameworks/support/+/androidx-main/compose/docs/compose-api-guidelines.md);
- [Compose API Reference](https://developer.android.com/reference/kotlin/androidx/compose);
- [Material Design 3 in Compose](https://developer.android.com/develop/ui/compose/designsystems/material3);
- [Material Design 3 Guidelines](https://m3.material.io/);
- [Android Security Best Practices](https://developer.android.com/privacy-and-security/security-best-practices).

## PROJECT FOUNDATIONS

### MODERN PROJECT STRUCTURE

- Example...

```log
android_project/
├── settings.gradle.kts
├── build.gradle.kts
├── gradle/libs.versions.toml
├── build-logic/
│   └── convention/
├── app/
│   └── src/main/
├── core/
│   ├── model/
│   ├── data/
│   ├── database/
│   ├── network/
│   ├── designsystem/
│   └── common/
├── feature/
│   ├── home/
│   ├── auth/
│   └── settings/
├── benchmark/
└── baselineprofile/

```

Use a modular structure when the app has multiple features, build variants, or teams. Keep the `app` module thin: it should own application startup, top-level navigation, dependency wiring, and build configuration. Put reusable models, repositories, data sources, database code, networking code, design system components, and feature screens in separate modules.

### GRADLE KOTLIN DSL & VERSION CATALOGS

- Example...

```kotlin
// settings.gradle.kts
dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        google()
        mavenCentral()
    }
}

// app/build.gradle.kts
plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.android)
    alias(libs.plugins.kotlin.compose)
    alias(libs.plugins.hilt)
}

```

Use Kotlin DSL, version catalogs, and convention plugins for every serious project. Never duplicate Android, Kotlin, Compose, lint, test, or dependency configuration across modules. Prefer the Compose BOM for Compose artifacts and keep AGP, Kotlin, Compose Compiler, Navigation, Hilt, Room, Material 3, WorkManager, and test library versions centralized.

### COMPOSE BILL OF MATERIALS

- Example...

```kotlin
dependencies {
    val composeBom = platform(libs.androidx.compose.bom)
    implementation(composeBom)
    androidTestImplementation(composeBom)

    implementation(libs.androidx.compose.ui)
    implementation(libs.androidx.compose.ui.tooling.preview)
    implementation(libs.androidx.compose.material3)
    debugImplementation(libs.androidx.compose.ui.tooling)
}

```

Use the Compose BOM to align Compose library versions. Do not manually pin every Compose artifact unless a specific artifact is intentionally outside the BOM. Keep `debugImplementation` dependencies such as Compose tooling out of release runtime dependencies.

### TARGET SDK & BUILD HYGIENE

- Example...

```kotlin
android {
    namespace = "com.example.app"
    compileSdk = libs.versions.android.compileSdk.get().toInt()

    defaultConfig {
        applicationId = "com.example.app"
        minSdk = libs.versions.android.minSdk.get().toInt()
        targetSdk = libs.versions.android.targetSdk.get().toInt()
    }
}

```

Target the latest stable Android SDK supported by your release channel and compile with the latest stable SDK available to your toolchain. Treat warnings from AGP, Kotlin, Compose, lint, and dependency analysis as actionable. Do not leave deprecated APIs, unchecked permissions, stale dependencies, or debug-only configuration in production code.

### ANDROID STUDIO & COMPOSE TOOLING

- Example...

```kotlin
@Preview(showBackground = true, widthDp = 360)
@Composable
private fun ProfileScreenPreview() {
    AppTheme {
        ProfileScreen(
            uiState = ProfileUiState.Content(ProfilePreviewData.user),
            onBackClick = {},
            onRetryClick = {},
        )
    }
}

```

Use Android Studio Compose tooling for previews, layout inspection, recomposition diagnostics, and screenshot-oriented UI checks. Keep previews deterministic: pass fake state, avoid real repositories, avoid real network calls, and render through the production theme.

## KOTLIN FOUNDATIONS

### GOOGLE ANDROID KOTLIN STYLE

- Example...

```kotlin
class UserRepository(
    private val localDataSource: UserLocalDataSource,
    private val remoteDataSource: UserRemoteDataSource,
) {
    suspend fun refreshUser(id: UserId): Result<User> = runCatching {
        remoteDataSource.fetchUser(id).also { user ->
            localDataSource.upsert(user)
        }
    }
}

```

Use the official Android Kotlin style guide and Kotlin coding conventions. Prefer clear names, small functions, constructor injection, trailing commas in multiline declarations, expression bodies only when they improve readability, and immutable values by default.

### NULL SAFETY & DOMAIN TYPES

- Example...

```kotlin
@JvmInline
value class UserId(val value: String)

data class User(
    val id: UserId,
    val name: String,
    val avatarUrl: String?,
)

```

Model optional data with nullable types only when absence is valid. Avoid `!!`, platform-type leakage, raw `String` identifiers, and map-shaped domain models. Use `data class`, `value class`, `enum class`, and `sealed interface` to make invalid states difficult to represent.

### UI STATE AS EXPLICIT TYPES

- Example...

```kotlin
sealed interface ProfileUiState {
    data object Loading : ProfileUiState
    data class Content(val user: UserUiModel) : ProfileUiState
    data class Error(val message: String) : ProfileUiState
}

```

Represent screen state explicitly. Do not scatter `isLoading`, nullable data, and nullable error fields across the UI when they can form impossible combinations. Use sealed state for mutually exclusive states and immutable data classes for renderable content.

## APP ARCHITECTURE

### RECOMMENDED LAYERS

- Example...

```log
UI LAYER
Composable screen -> ViewModel -> UiState

OPTIONAL DOMAIN LAYER
UseCase / Interactor -> reusable business rule

DATA LAYER
Repository -> LocalDataSource / RemoteDataSource

```

Follow Android's recommended app architecture. The UI layer displays state and sends events. The data layer owns application data and business rules. Add a domain layer only when business logic is complex or reused by multiple ViewModels. Do not let Composables call network clients, DAOs, DataStore, file APIs, or storage APIs directly.

### VIEWMODEL AS SCREEN STATE HOLDER

- Example...

```kotlin
@HiltViewModel
class ProfileViewModel @Inject constructor(
    private val observeProfile: ObserveProfileUseCase,
    savedStateHandle: SavedStateHandle,
) : ViewModel() {
    private val userId = checkNotNull(savedStateHandle["userId"])

    val uiState: StateFlow<ProfileUiState> = observeProfile(userId)
        .map<Profile, ProfileUiState> { profile ->
            ProfileUiState.Content(profile.toUiModel())
        }
        .catch { emit(ProfileUiState.Error("Unable to load profile")) }
        .stateIn(
            scope = viewModelScope,
            started = SharingStarted.WhileSubscribed(5_000),
            initialValue = ProfileUiState.Loading,
        )
}

```

Use `ViewModel` for screen-level state and business logic coordination. Expose immutable `StateFlow` or immutable state objects. Keep mutable state private. Never keep an `Activity`, `Fragment`, `View`, or long-lived `Context` reference inside a ViewModel.

### UNIDIRECTIONAL DATA FLOW

- Example...

```kotlin
@Composable
fun ProfileRoute(
    viewModel: ProfileViewModel = hiltViewModel(),
    onBackClick: () -> Unit,
) {
    val uiState by viewModel.uiState.collectAsStateWithLifecycle()

    ProfileScreen(
        uiState = uiState,
        onBackClick = onBackClick,
        onRetryClick = viewModel::retry,
    )
}

```

Use unidirectional data flow. State flows down from ViewModel to Composables. Events flow up from Composables to callbacks. Avoid two-way binding, global mutable singletons, and direct mutation of shared state from UI elements.

## JETPACK COMPOSE MENTAL MODEL

### THINKING IN COMPOSE

- Example...

```kotlin
@Composable
fun Greeting(name: String, modifier: Modifier = Modifier) {
    Text(
        text = "Hello, $name",
        modifier = modifier,
    )
}

```

Compose is declarative. Describe the UI for the current state; do not imperatively mutate a view tree. Composables can recompose frequently, in different orders, or be skipped when inputs are stable. Keep Composables fast, deterministic, and free of uncontrolled side effects.

### COMPOSABLE LIFECYCLE

- Example...

```kotlin
@Composable
fun UserAvatar(userId: UserId, imageLoader: ImageLoader) {
    DisposableEffect(userId) {
        val handle = imageLoader.prefetch(userId.value)
        onDispose { handle.cancel() }
    }
}

```

A Composable enters the composition, may recompose many times, and eventually leaves the composition. Tie registration, cleanup, and coroutine work to the correct lifecycle with Compose effect APIs. Do not assume a Composable body runs exactly once.

### COMPOSE PHASES

- Example...

```kotlin
Image(
    painter = painter,
    contentDescription = null,
    modifier = Modifier.offset {
        IntOffset(x = listState.firstVisibleItemScrollOffset / 2, y = 0)
    },
)

```

Understand the three rendering phases: composition decides what UI to show, layout measures and places it, and drawing renders it. Read rapidly changing state in the latest suitable phase. For scroll-linked offsets and drawing effects, prefer lambda-based layout or drawing modifiers when they avoid unnecessary recomposition.

### ARCHITECTURAL LAYERING IN COMPOSE

- Example...

```log
Material component
Foundation primitive
Runtime state model
Compiler/runtime

```

Compose is layered. Use Material 3 components for normal app UI, foundation primitives for custom design systems, and low-level layout/drawing APIs only when Material or foundation APIs are insufficient. Do not rebuild accessible Material behavior from scratch unless the product requirement justifies the cost.

## JETPACK COMPOSE UI

### STATELESS COMPOSABLES

- Example...

```kotlin
@Composable
fun ProfileScreen(
    uiState: ProfileUiState,
    onBackClick: () -> Unit,
    onRetryClick: () -> Unit,
    modifier: Modifier = Modifier,
) {
    when (uiState) {
        ProfileUiState.Loading -> LoadingContent(modifier)
        is ProfileUiState.Content -> ProfileContent(uiState.user, onBackClick, modifier)
        is ProfileUiState.Error -> ErrorContent(uiState.message, onRetryClick, modifier)
    }
}

```

Make screen Composables stateless whenever possible. Pass state and events explicitly. Put `modifier: Modifier = Modifier` in public Composable APIs. Do not start network requests, database writes, permission requests, navigation actions, or analytics calls directly in the body of a Composable.

### STATE HOISTING

- Example...

```kotlin
@Composable
fun SearchField(
    query: String,
    onQueryChange: (String) -> Unit,
    modifier: Modifier = Modifier,
) {
    OutlinedTextField(
        value = query,
        onValueChange = onQueryChange,
        modifier = modifier,
        singleLine = true,
    )
}

```

Hoist state to the lowest common owner that reads and writes it. Keep transient UI element state close to the Composable with `rememberSaveable` when it is purely UI state. Hoist screen data and business logic state to a ViewModel.

### COMPOSE SIDE EFFECTS

- Example...

```kotlin
@Composable
fun AnalyticsScreenEffect(
    screenName: String,
    analytics: Analytics,
) {
    val currentScreenName by rememberUpdatedState(screenName)

    LaunchedEffect(Unit) {
        analytics.logScreenView(currentScreenName)
    }
}

```

Use Compose side-effect APIs deliberately. Use `LaunchedEffect` for suspend side effects tied to composition, `DisposableEffect` for registration and cleanup, `rememberUpdatedState` for updated lambdas or values inside long-lived effects, `produceState` for converting external observable sources into Compose state, and `derivedStateOf` for expensive derived values that should update only when inputs change.

### MODIFIERS

- Example...

```kotlin
@Composable
fun ArticleCard(
    article: ArticleUiModel,
    modifier: Modifier = Modifier,
) {
    Card(modifier = modifier.fillMaxWidth()) {
        Text(
            text = article.title,
            modifier = Modifier.padding(16.dp),
        )
    }
}

```

Every reusable UI element should accept a `modifier` parameter and apply it to the first meaningful UI node. Modifier order is semantic: layout, input, drawing, clipping, and semantics modifiers can produce different behavior depending on order. Prefer chaining existing modifiers before writing custom modifier behavior; use `Modifier.Node` only for lower-level performance-sensitive custom modifiers.

### SEMANTICS & ACCESSIBILITY TREE

- Example...

```kotlin
Row(
    modifier = Modifier.semantics(mergeDescendants = true) {},
) {
    Text(article.title)
    Text(article.subtitle)
}

```

Use semantics to expose meaning to accessibility services and Compose tests. Prefer user-visible text, roles, content descriptions, state descriptions, and merged semantics over arbitrary test tags. Custom components must provide the same semantic clarity as Material components.

### COMPOSITIONLOCAL

- Example...

```kotlin
val LocalAnalytics = staticCompositionLocalOf<Analytics> {
    error("Analytics is not provided")
}

@Composable
fun AppProviders(
    analytics: Analytics,
    content: @Composable () -> Unit,
) {
    CompositionLocalProvider(LocalAnalytics provides analytics) {
        content()
    }
}

```

Use `CompositionLocal` sparingly for truly tree-scoped dependencies such as theme tokens, layout direction, density, permission controllers, or app-level services. Do not use it as a hidden service locator for repositories, mutable business state, or arbitrary dependencies that should be explicit parameters.

### LAZY LISTS & STABLE KEYS

- Example...

```kotlin
LazyColumn {
    items(
        items = articles,
        key = { article -> article.id.value },
        contentType = { "article" },
    ) { article ->
        ArticleCard(article = article)
    }
}

```

Always provide stable keys for lazy list items that can be inserted, removed, or reordered. Use `contentType` when rows have different layouts. Avoid heavy sorting, filtering, allocation, or formatting inside item lambdas.

## COMPOSE DESIGN & UI CAPABILITIES

### LAYOUTS

- Example...

```kotlin
Column(
    modifier = Modifier
        .fillMaxSize()
        .padding(16.dp),
    verticalArrangement = Arrangement.spacedBy(12.dp),
) {
    Header(title = uiState.title)
    Content(items = uiState.items)
}

```

Use standard layout primitives such as `Row`, `Column`, `Box`, lazy lists, lazy grids, and Material scaffolds before custom layout code. Reach for `ConstraintLayout` only when it simplifies genuinely constraint-heavy screens. Avoid deeply nested layouts that obscure ownership of spacing and alignment.

### CUSTOM LAYOUTS & INTRINSICS

- Example...

```kotlin
@Composable
fun TwoColumnLayout(
    left: @Composable () -> Unit,
    right: @Composable () -> Unit,
    modifier: Modifier = Modifier,
) {
    Layout(
        content = {
            left()
            right()
        },
        modifier = modifier,
    ) { measurables, constraints ->
        val halfWidth = constraints.maxWidth / 2
        val childConstraints = constraints.copy(maxWidth = halfWidth)
        val leftPlaceable = measurables[0].measure(childConstraints)
        val rightPlaceable = measurables[1].measure(childConstraints)

        layout(constraints.maxWidth, maxOf(leftPlaceable.height, rightPlaceable.height)) {
            leftPlaceable.placeRelative(0, 0)
            rightPlaceable.placeRelative(halfWidth, 0)
        }
    }
}

```

Use custom layouts only when built-in layouts cannot express the design cleanly. Remember that Compose measures children once per pass. Use intrinsic measurements only when the layout requirement truly needs information before normal measurement because they can add cost and complexity.

### TEXT & RESOURCES

- Example...

```kotlin
Text(
    text = stringResource(R.string.profile_title),
    style = MaterialTheme.typography.titleLarge,
)

```

Use Android resources for user-facing strings, plurals, dimensions that must be shared with XML/platform APIs, and localized content. Use Compose resource APIs from Composables. Do not hardcode user-visible strings, layout direction assumptions, or locale-specific formatting.

### GRAPHICS & DRAWING

- Example...

```kotlin
Box(
    modifier = Modifier.drawWithCache {
        val brush = Brush.verticalGradient(listOf(Color.Transparent, Color.Black))
        onDrawWithContent {
            drawContent()
            drawRect(brush)
        }
    },
)

```

Use `graphicsLayer`, `drawBehind`, `drawWithContent`, `drawWithCache`, `Canvas`, and vector drawables intentionally. Cache expensive drawing objects. Do not use drawing APIs to fake semantics or interaction behavior that should be represented by real components.

### ANIMATION

- Example...

```kotlin
AnimatedVisibility(visible = uiState.showDetails) {
    DetailsPanel(uiState.details)
}

```

Use Compose animation APIs to describe state-driven motion. Prefer high-level APIs such as `AnimatedVisibility`, `AnimatedContent`, `animate*AsState`, and `updateTransition` before low-level animation clocks. Keep animations meaningful, interruptible, and respectful of accessibility settings.

### GESTURES & INTERACTIONS

- Example...

```kotlin
val interactionSource = remember { MutableInteractionSource() }

Card(
    onClick = onClick,
    interactionSource = interactionSource,
) {
    Text(text = item.title)
}

```

Prefer Material components and high-level gesture modifiers such as `clickable`, `combinedClickable`, `draggable`, and `scrollable`. Use `pointerInput` only for custom gesture logic. Preserve accessibility semantics, focus behavior, ripple/indication expectations, and keyboard interaction when customizing input.

## MATERIAL YOU & MATERIAL 3

### MATERIAL 3 THEME

- Example...

```kotlin
@Composable
fun AppTheme(
    darkTheme: Boolean = isSystemInDarkTheme(),
    dynamicColor: Boolean = true,
    content: @Composable () -> Unit,
) {
    val context = LocalContext.current
    val colorScheme = when {
        dynamicColor && Build.VERSION.SDK_INT >= Build.VERSION_CODES.S -> {
            if (darkTheme) dynamicDarkColorScheme(context) else dynamicLightColorScheme(context)
        }
        darkTheme -> DarkColorScheme
        else -> LightColorScheme
    }

    MaterialTheme(
        colorScheme = colorScheme,
        typography = AppTypography,
        shapes = AppShapes,
        content = content,
    )
}

```

Use Material 3 as the default Compose design system. Support dark theme and dynamic color where available. Do not hardcode arbitrary colors inside feature screens. Use semantic color roles from `MaterialTheme.colorScheme`, typography from `MaterialTheme.typography`, and shapes from `MaterialTheme.shapes`.

### DESIGN SYSTEM MODULE

- Example...

```log
core/designsystem/
├── component/
├── icon/
├── theme/
│   ├── Color.kt
│   ├── Shape.kt
│   ├── Theme.kt
│   └── Type.kt
└── preview/

```

Create a design system module for shared theme, components, icons, previews, and reusable layout primitives. Feature modules should consume the design system; they should not define independent button styles, color constants, typography scales, or one-off component variants.

### MATERIAL COMPONENTS & DESIGN SYSTEMS

- Example...

```kotlin
Scaffold(
    topBar = { TopAppBar(title = { Text(stringResource(R.string.app_name)) }) },
    floatingActionButton = { FloatingActionButton(onClick = onCreateClick) { Icon(Icons.Default.Add, null) } },
) { paddingValues ->
    HomeContent(
        uiState = uiState,
        modifier = Modifier.padding(paddingValues),
    )
}

```

Prefer Material 3 components for navigation, app bars, buttons, cards, dialogs, sheets, text fields, menus, and progress indicators. Customize through theme tokens and component parameters before creating custom components. If migrating from Material 2, do it deliberately and avoid mixing M2 and M3 components without a transition plan.

## ADAPTIVE UI

### WINDOW SIZE CLASSES

- Example...

```kotlin
@Composable
fun FeedPane(
    windowSizeClass: WindowSizeClass,
    uiState: FeedUiState,
) {
    if (windowSizeClass.windowWidthSizeClass == WindowWidthSizeClass.EXPANDED) {
        FeedListDetailPane(uiState)
    } else {
        FeedSinglePane(uiState)
    }
}

```

Design for the app window size, not only the physical device. Support phones, tablets, foldables, ChromeOS, landscape, split-screen, desktop windowing, and external displays. Use window size classes and Material 3 adaptive components for canonical multi-pane layouts.

### MATERIAL 3 ADAPTIVE SCAFFOLDS

- Example...

```kotlin
@Composable
fun AdaptiveApp(content: @Composable () -> Unit) {
    NavigationSuiteScaffold(
        navigationSuiteItems = {
            item(
                selected = true,
                onClick = {},
                icon = { Icon(Icons.Default.Home, contentDescription = null) },
                label = { Text("Home") },
            )
        },
    ) {
        content()
    }
}

```

Use Material 3 Adaptive where it fits: `NavigationSuiteScaffold` for responsive navigation, `ListDetailPaneScaffold` for list-detail flows, and `SupportingPaneScaffold` for secondary content. Preserve continuity across resizing, orientation changes, posture changes, and multi-window mode.

### ADAPTIVE DO'S AND DON'TS

- Example...

```xml
<activity
    android:name=".MainActivity"
    android:exported="true" />

```

Do not lock orientation or opt out of resizing to avoid layout work. Adaptive apps must handle window changes, fold/unfold posture changes, font scaling, density changes, and split-screen behavior. Save state with `rememberSaveable`, `ViewModel`, and persistent storage where appropriate.

## DATA, STORAGE & BACKGROUND WORK

### REPOSITORIES AS DATA OWNERS

- Example...

```kotlin
class OfflineFirstArticleRepository @Inject constructor(
    private val localDataSource: ArticleLocalDataSource,
    private val remoteDataSource: ArticleRemoteDataSource,
) : ArticleRepository {
    override fun observeArticles(): Flow<List<Article>> = localDataSource.observeArticles()

    override suspend fun sync() {
        val remoteArticles = remoteDataSource.fetchArticles()
        localDataSource.upsertAll(remoteArticles)
    }
}

```

Use repositories as the public API for app data. In offline-first features, make the local database the source of truth and synchronize network data into it. Do not expose raw DTOs, database entities, or network response wrappers to the UI.

### ROOM FOR STRUCTURED DATA

- Example...

```kotlin
@Dao
interface ArticleDao {
    @Query("SELECT * FROM articles ORDER BY publishedAt DESC")
    fun observeArticles(): Flow<List<ArticleEntity>>

    @Upsert
    suspend fun upsertAll(articles: List<ArticleEntity>)
}

```

Use Room for structured local persistence. Prefer observable queries with `Flow`. Keep entities local to the database module and map them to domain models before they reach repositories or UI state.

### DATASTORE FOR SMALL PREFERENCES

- Example...

```kotlin
val userPreferences: Flow<UserPreferences> = dataStore.data
    .map { preferences ->
        UserPreferences(
            useDynamicColor = preferences[USE_DYNAMIC_COLOR] ?: true,
        )
    }

```

Use DataStore instead of SharedPreferences for small key-value preferences or typed settings. Keep DataStore access in the data layer. Do not read preferences synchronously on the main thread. Use Room instead when you need large datasets, partial updates, queries, or referential integrity.

### WORKMANAGER FOR RELIABLE DEFERRABLE WORK

- Example...

```kotlin
val request = OneTimeWorkRequestBuilder<SyncWorker>()
    .setConstraints(
        Constraints.Builder()
            .setRequiredNetworkType(NetworkType.CONNECTED)
            .build()
    )
    .build()

workManager.enqueueUniqueWork(
    "sync",
    ExistingWorkPolicy.KEEP,
    request,
)

```

Use WorkManager for persistent, deferrable background work that must survive process death or device reboot. Do not use it for immediate in-process work, exact alarms, foreground UI work, or long-running networking that belongs in a repository call.

## COROUTINES & FLOW

### MAIN-SAFE SUSPEND FUNCTIONS

- Example...

```kotlin
class ImageRepository @Inject constructor(
    @IoDispatcher private val ioDispatcher: CoroutineDispatcher,
) {
    suspend fun decodeImage(bytes: ByteArray): Image = withContext(ioDispatcher) {
        decoder.decode(bytes)
    }
}

```

Make suspend functions main-safe. The caller should not need to know which dispatcher is required. Inject dispatchers so tests can control execution. Never use `GlobalScope` for application logic.

### IMMUTABLE FLOW EXPOSURE

- Example...

```kotlin
private val _events = MutableSharedFlow<ProfileEvent>()
val events: SharedFlow<ProfileEvent> = _events.asSharedFlow()

private val _uiState = MutableStateFlow(ProfileUiState.Loading)
val uiState: StateFlow<ProfileUiState> = _uiState.asStateFlow()

```

Expose immutable `Flow`, `StateFlow`, or `SharedFlow` from ViewModels and repositories. Keep mutable streams private. Use `StateFlow` for observable state and `SharedFlow` or channels for one-off events when needed.

### LIFECYCLE-AWARE COLLECTION

- Example...

```kotlin
@Composable
fun SettingsRoute(viewModel: SettingsViewModel = hiltViewModel()) {
    val uiState by viewModel.uiState.collectAsStateWithLifecycle()
    SettingsScreen(uiState = uiState)
}

```

Collect flows from Compose with lifecycle awareness. Prefer `collectAsStateWithLifecycle` in Android UI. Do not collect long-lived flows in Composables without lifecycle handling.

## NAVIGATION & APP FLOW

### TYPE-SAFE NAVIGATION

- Example...

```kotlin
@Serializable
data class ProfileRoute(val userId: String)

composable<ProfileRoute> { backStackEntry ->
    val route = backStackEntry.toRoute<ProfileRoute>()
    ProfileRoute(userId = route.userId)
}

```

Use type-safe Navigation Compose routes instead of fragile string route concatenation. Keep navigation decisions at screen or app level. Composables should receive callbacks such as `onProfileClick(userId)` rather than a raw `NavController` unless they are navigation host code.

### MULTI-MODULE NAVIGATION

- Example...

```kotlin
fun NavGraphBuilder.homeScreen(
    onArticleClick: (ArticleId) -> Unit,
) {
    composable<HomeRoute> {
        HomeRoute(onArticleClick = onArticleClick)
    }
}

```

Let feature modules expose navigation entry functions and route types. Let the app module connect features into the final graph. Do not make feature modules depend on each other through concrete implementation details.

## ADOPTING & MIGRATING TO COMPOSE

### INCREMENTAL MIGRATION

- Example...

```kotlin
class LegacyProfileFragment : Fragment(R.layout.legacy_profile) {
    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        view.findViewById<ComposeView>(R.id.compose_content).setContent {
            AppTheme {
                ProfileRoute(onBackClick = { findNavController().popBackStack() })
            }
        }
    }
}

```

Migrate view-based apps incrementally. Use Compose in isolated screens or leaf UI components first, then expand as architecture, theming, testing, and navigation are ready. Do not mix View and Compose state ownership without an explicit boundary.

### INTEROPERABILITY APIs

- Example...

```kotlin
AndroidView(
    factory = { context -> LegacyChartView(context) },
    update = { chart -> chart.submitData(uiState.chartData) },
)

```

Use interoperability APIs when a required View-based component has no Compose equivalent. Keep interop at boundaries and avoid spreading `AndroidView`, `ComposeView`, or Fragment-specific logic throughout feature code.

### COMPOSE AND VIEW-BASED LIBRARIES

- Example...

```kotlin
@Composable
fun MapContainer(
    state: MapUiState,
    modifier: Modifier = Modifier,
) {
    AndroidView(
        modifier = modifier,
        factory = { context -> MapView(context) },
        update = { mapView -> mapView.render(state) },
    )
}

```

Wrap view-based libraries behind stable Composable APIs. Own lifecycle, cleanup, state synchronization, and accessibility behavior explicitly. Prefer Compose-native libraries when they are mature enough for the use case.

## TESTING & CODE QUALITY

### UNIT TEST VIEWMODELS AND REPOSITORIES

- Example...

```kotlin
@Test
fun loadingArticlesEmitsContent() = runTest {
    val repository = FakeArticleRepository()
    val viewModel = HomeViewModel(repository)

    repository.emitArticles(listOf(articleFixture()))

    assertEquals(HomeUiState.Content(listOf(articleUiFixture())), viewModel.uiState.value)
}

```

Test ViewModels, repositories, use cases, mappers, validators, and reducers with fake dependencies. Avoid tests that require real network, real time, uncontrolled dispatchers, or shared mutable state.

### COMPOSE UI TESTS

- Example...

```kotlin
@get:Rule
val composeTestRule = createComposeRule()

@Test
fun retryButtonIsShownForErrorState() {
    composeTestRule.setContent {
        AppTheme {
            ProfileScreen(
                uiState = ProfileUiState.Error("Network error"),
                onBackClick = {},
                onRetryClick = {},
            )
        }
    }

    composeTestRule.onNodeWithText("Network error").assertIsDisplayed()
    composeTestRule.onNodeWithText("Retry").assertIsDisplayed()
}

```

Test Compose UI through semantics. Prefer visible text, content descriptions, semantic roles, and stable test tags only when user-visible semantics are not enough. Keep screen tests deterministic by passing explicit state.

### TESTING CHEAT SHEET HABITS

- Example...

```kotlin
composeTestRule
    .onNodeWithContentDescription("Navigate back")
    .assertHasClickAction()
    .performClick()

```

Use Compose testing APIs consistently: find nodes by semantic meaning, assert state before action, perform one user action, then assert the resulting UI. Avoid implementation-detail tests that break when layout structure changes but user behavior does not.

### LINT, STATIC ANALYSIS & CI

- Example...

```bash
./gradlew lint testDebugUnitTest connectedDebugAndroidTest
./gradlew :benchmark:connectedCheck
./gradlew :baselineprofile:generateBaselineProfile

```

Run lint, unit tests, instrumented tests, Compose UI tests, and benchmark/profile tasks in CI. Treat new lint errors as build failures. Keep release builds minified, resource-shrunk, signed, and reproducible.

## PROFILING & PERFORMANCE

### COMPOSE PERFORMANCE RULES

- Example...

```kotlin
val filteredItems by remember(items, query) {
    derivedStateOf {
        items.filter { item -> item.title.contains(query, ignoreCase = true) }
    }
}

```

Do as little work as possible inside Composable bodies. Use `remember` for expensive calculations, `derivedStateOf` for derived state, stable lazy list keys, `contentType`, immutable UI models, and phase-aware state reads. Measure before optimizing; do not guess.

### STABILITY & RECOMPOSITION

- Example...

```kotlin
@Immutable
data class ArticleUiModel(
    val id: String,
    val title: String,
    val subtitle: String,
)

```

Prefer immutable UI models with stable types. Avoid mutable collections in state exposed to Compose. Use Compose compiler reports and Layout Inspector when diagnosing unexpected recomposition. Do not add stability annotations to hide mutable behavior.

### BASELINE PROFILES & MACROBENCHMARKS

- Example...

```kotlin
@HiltAndroidTest
@RunWith(AndroidJUnit4::class)
class StartupBaselineProfile {
    @get:Rule
    val baselineProfileRule = BaselineProfileRule()

    @Test
    fun generate() = baselineProfileRule.collect(packageName = "com.example.app") {
        pressHome()
        startActivityAndWait()
    }
}

```

Generate Baseline Profiles for critical startup and user journeys. Use Macrobenchmark to verify startup, scrolling, navigation, and animation performance on release-like builds. Never evaluate Compose performance only from debug builds.

### COMPARE COMPOSE AND VIEW METRICS

- Example...

```bash
./gradlew :app:assembleRelease
./gradlew :benchmark:connectedCheck

```

When migrating from Views to Compose, measure APK size, startup, scrolling, memory, and frame timing before and after migration. Do not assume migration is performance-neutral; use release builds, baseline profiles, and macrobenchmarks.

## ACCESSIBILITY, PRIVACY & SECURITY

### ACCESSIBLE COMPOSE UI

- Example...

```kotlin
IconButton(onClick = onBackClick) {
    Icon(
        imageVector = Icons.AutoMirrored.Filled.ArrowBack,
        contentDescription = "Navigate back",
    )
}

```

Build accessibility into every screen. Provide labels for meaningful icons and interactive elements, use Material components when possible, support scalable text, maintain sufficient contrast, avoid color-only meaning, preserve focus order, and validate custom components with semantics.

### PERMISSIONS MINIMIZATION

- Example...

```xml
<uses-permission android:name="android.permission.CAMERA" />

```

Request permissions only when a feature genuinely needs restricted data or actions. Prefer platform alternatives that avoid permissions. Explain permission-dependent actions in context and handle denial without trapping the user.

### NETWORK SECURITY

- Example...

```xml
<network-security-config>
    <base-config cleartextTrafficPermitted="false" />
</network-security-config>

```

Use HTTPS by default and disable cleartext traffic unless a specific debug-only exception is required. Use Network Security Configuration for declarative trust settings. Do not bypass TLS validation, accept all certificates, or ship debug trust anchors in release builds.

### SECRET MANAGEMENT

- Example...

```kotlin
val keyStore = KeyStore.getInstance("AndroidKeyStore").apply {
    load(null)
}

```

Never hardcode API secrets, signing keys, cryptographic keys, or privileged backend credentials in the APK. Use server-side authorization for real secrets and Android Keystore for local cryptographic keys when device-side key storage is required.

### BACKUP & DATA EXPOSURE

- Example...

```xml
<application
    android:dataExtractionRules="@xml/data_extraction_rules"
    android:fullBackupContent="@xml/backup_rules">
</application>

```

Define backup and data extraction rules deliberately. Exclude sensitive files, tokens, caches, and local databases that should not migrate across devices. Disable backup only when the app can recreate state safely or handles sensitive data that must never be backed up.

## COMPOSE DOCUMENTATION MAP

### FOUNDATION

- [Thinking in Compose](https://developer.android.com/develop/ui/compose/mental-model);
- [Managing state](https://developer.android.com/develop/ui/compose/state);
- [Lifecycle of composables](https://developer.android.com/develop/ui/compose/lifecycle);
- [Modifiers](https://developer.android.com/develop/ui/compose/modifiers);
- [Side-effects in Compose](https://developer.android.com/develop/ui/compose/side-effects);
- [Jetpack Compose phases](https://developer.android.com/develop/ui/compose/phases);
- [Architectural layering](https://developer.android.com/develop/ui/compose/layering);
- [Performance](https://developer.android.com/develop/ui/compose/performance);
- [Semantics in Compose](https://developer.android.com/develop/ui/compose/semantics);
- [CompositionLocal](https://developer.android.com/develop/ui/compose/compositionlocal).

### ADAPTIVE UI

- [Build adaptive apps](https://developer.android.com/develop/adaptive-apps/guides/build-adaptive-apps);
- [Adaptive layouts](https://developer.android.com/develop/ui/compose/layouts/adaptive);
- [Use window size classes](https://developer.android.com/develop/ui/compose/layouts/adaptive/use-window-size-classes);
- [Canonical layouts](https://developer.android.com/develop/adaptive-apps/guides/canonical-layouts);
- [Adaptive do's and don'ts](https://developer.android.com/develop/ui/compose/layouts/adaptive/adaptive-dos-and-donts);
- [Adaptive navigation](https://developer.android.com/guide/topics/large-screens/navigation-for-responsive-uis);
- [Compose Material 3 Adaptive](https://developer.android.com/jetpack/androidx/releases/compose-material3-adaptive).

### DEVELOPMENT ENVIRONMENT

- [Android Studio with Compose](https://developer.android.com/develop/ui/compose/setup);
- [Tooling for Compose](https://developer.android.com/develop/ui/compose/tooling);
- [Kotlin for Compose](https://developer.android.com/develop/ui/compose/kotlin);
- [Compare Compose and view metrics](https://developer.android.com/develop/ui/compose/migrate/compare-metrics);
- [Compose Bill of Materials](https://developer.android.com/develop/ui/compose/bom).

### DESIGN

- [Layouts](https://developer.android.com/develop/ui/compose/layouts);
- [Layout basics](https://developer.android.com/develop/ui/compose/layouts/basics);
- [Material components and layouts](https://developer.android.com/develop/ui/compose/components);
- [Custom layouts](https://developer.android.com/develop/ui/compose/layouts/custom);
- [Alignment lines](https://developer.android.com/develop/ui/compose/layouts/alignment-lines);
- [Intrinsic measurements](https://developer.android.com/develop/ui/compose/layouts/intrinsic-measurements);
- [ConstraintLayout in Compose](https://developer.android.com/develop/ui/compose/layouts/constraintlayout);
- [Design systems](https://developer.android.com/develop/ui/compose/designsystems);
- [Material Design 3 in Compose](https://developer.android.com/develop/ui/compose/designsystems/material3);
- [Migrating from Material 2 to Material 3](https://developer.android.com/develop/ui/compose/designsystems/material2-material3);
- [Material Design 2 in Compose](https://developer.android.com/develop/ui/compose/designsystems/material);
- [Custom design systems](https://developer.android.com/develop/ui/compose/designsystems/custom);
- [Anatomy of a theme](https://developer.android.com/develop/ui/compose/designsystems/anatomy);
- [Lists and grids](https://developer.android.com/develop/ui/compose/lists);
- [Text](https://developer.android.com/develop/ui/compose/text);
- [Graphics](https://developer.android.com/develop/ui/compose/graphics);
- [Animation](https://developer.android.com/develop/ui/compose/animation/introduction);
- [Gestures](https://developer.android.com/develop/ui/compose/touch-input/pointer-input);
- [Handling user interactions](https://developer.android.com/develop/ui/compose/touch-input/user-interactions/handling-interactions).

### ADOPTING COMPOSE

- [Migrate view-based apps](https://developer.android.com/develop/ui/compose/migrate);
- [Migration strategy](https://developer.android.com/develop/ui/compose/migrate/strategy);
- [Interoperability APIs](https://developer.android.com/develop/ui/compose/migrate/interoperability-apis);
- [Other migration considerations](https://developer.android.com/develop/ui/compose/migrate/other-considerations);
- [Compose and other libraries](https://developer.android.com/develop/ui/compose/libraries);
- [Compose architecture](https://developer.android.com/develop/ui/compose/architecture);
- [Navigation in Compose](https://developer.android.com/develop/ui/compose/navigation);
- [Resources in Compose](https://developer.android.com/develop/ui/compose/resources);
- [Accessibility in Compose](https://developer.android.com/develop/ui/compose/accessibility);
- [Testing Compose](https://developer.android.com/develop/ui/compose/testing);
- [Compose testing cheat sheet](https://developer.android.com/develop/ui/compose/testing-cheatsheet).

### LEARNING & SAMPLES

- [Compose learning pathway](https://developer.android.com/courses/pathways/compose);
- [Compose codelabs](https://goo.gle/compose-codelabs);
- [Compose samples](https://github.com/android/compose-samples);
- [Android Developers Compose videos](https://www.youtube.com/user/androiddevelopers/search?query=%23jetpackcompose).

## API & REFERENCES

- [Android Developers](https://developer.android.com/);
- [Android Architecture](https://developer.android.com/topic/architecture);
- [Android Architecture Recommendations](https://developer.android.com/topic/architecture/recommendations);
- [UI Layer](https://developer.android.com/topic/architecture/ui-layer);
- [Data Layer](https://developer.android.com/topic/architecture/data-layer);
- [Domain Layer](https://developer.android.com/topic/architecture/domain-layer);
- [ViewModel](https://developer.android.com/topic/libraries/architecture/viewmodel);
- [Kotlin Coroutines on Android](https://developer.android.com/kotlin/coroutines);
- [Coroutines Best Practices](https://developer.android.com/kotlin/coroutines/coroutines-best-practices);
- [Kotlin Flow on Android](https://developer.android.com/kotlin/flow);
- [StateFlow and SharedFlow](https://developer.android.com/kotlin/flow/stateflow-and-sharedflow);
- [Jetpack Compose](https://developer.android.com/develop/ui/compose);
- [Compose API Guidelines](https://android.googlesource.com/platform/frameworks/support/+/androidx-main/compose/docs/compose-api-guidelines.md);
- [Compose API Reference](https://developer.android.com/reference/kotlin/androidx/compose);
- [Material 3 in Compose](https://developer.android.com/develop/ui/compose/designsystems/material3);
- [Material Design 3](https://m3.material.io/);
- [Dynamic Color](https://m3.material.io/styles/color/dynamic);
- [Material 3 Color Roles](https://m3.material.io/styles/color/roles);
- [Navigation Compose](https://developer.android.com/develop/ui/compose/navigation);
- [Type-Safe Navigation](https://developer.android.com/guide/navigation/design/type-safety);
- [Room](https://developer.android.com/training/data-storage/room);
- [DataStore](https://developer.android.com/topic/libraries/architecture/datastore);
- [WorkManager](https://developer.android.com/develop/background-work/background-tasks/persistent/getting-started);
- [Hilt](https://developer.android.com/training/dependency-injection/hilt-android);
- [Hilt Jetpack Integrations](https://developer.android.com/training/dependency-injection/hilt-jetpack);
- [Android Lint](https://developer.android.com/studio/write/lint);
- [Baseline Profiles](https://developer.android.com/topic/performance/baselineprofiles/overview);
- [Macrobenchmark](https://developer.android.com/topic/performance/benchmarking/macrobenchmark-overview);
- [Android Security Best Practices](https://developer.android.com/privacy-and-security/security-best-practices);
- [Android Permissions](https://developer.android.com/guide/topics/permissions/overview);
- [Network Security Configuration](https://developer.android.com/privacy-and-security/security-config);
- [Android Accessibility](https://developer.android.com/develop/ui/compose/accessibility).
