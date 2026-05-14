package com.local.glucotracker.ui.navigation

import androidx.compose.animation.EnterTransition
import androidx.compose.animation.ExitTransition
import androidx.compose.animation.core.LinearOutSlowInEasing
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.slideInVertically
import androidx.compose.animation.core.tween
import androidx.compose.foundation.Image
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.pager.HorizontalPager
import androidx.compose.foundation.pager.rememberPagerState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.navigation.NavGraph.Companion.findStartDestination
import androidx.navigation.NavHostController
import androidx.navigation.NavType
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.compose.rememberNavController
import androidx.navigation.navArgument
import androidx.navigation.navDeepLink
import com.local.glucotracker.R
import com.local.glucotracker.ui.design.GT
import com.local.glucotracker.ui.design.primitives.GTBrandLockup
import com.local.glucotracker.ui.design.primitives.GTBottomBar
import com.local.glucotracker.ui.design.primitives.GTBottomBarItem
import com.local.glucotracker.ui.design.primitives.GTFab
import com.local.glucotracker.ui.design.primitives.GTHintBox
import com.local.glucotracker.ui.design.primitives.GTKicker
import com.local.glucotracker.ui.design.primitives.GTOutlineButton
import com.local.glucotracker.ui.feature.auth.AuthGateState
import com.local.glucotracker.ui.feature.auth.AuthGateViewModel
import com.local.glucotracker.ui.feature.auth.LoginRoute
import com.local.glucotracker.ui.feature.base.BaseRoute
import com.local.glucotracker.ui.feature.capture.GTComposeSheet
import com.local.glucotracker.ui.feature.capture.PhotoCaptureScreen
import com.local.glucotracker.ui.feature.history.HistoryRoute
import com.local.glucotracker.ui.feature.more.MoreRoute
import com.local.glucotracker.ui.feature.record.RecordRoute
import com.local.glucotracker.ui.feature.stack.MealStackRoute
import com.local.glucotracker.ui.feature.sync.OutboxInspectorRoute
import com.local.glucotracker.ui.feature.stats.StatsRoute
import com.local.glucotracker.ui.feature.today.TodayRoute
import com.local.glucotracker.ui.glucose.GlucoseSurfaces
import com.local.glucotracker.ui.glucose.GlucoseSurfacesNoop
import com.local.glucotracker.ui.glucose.LocalGlucoseSurfaces
import kotlinx.coroutines.launch
import kotlinx.datetime.LocalDate

@Composable
fun GlucotrackerApp(
    authGateViewModel: AuthGateViewModel = hiltViewModel(),
) {
    val authState by authGateViewModel.state.collectAsStateWithLifecycle()
    when (authState) {
        AuthGateState.Loading -> {
            Box(
                modifier = Modifier
                    .fillMaxSize()
                    .background(GT.colors.bg),
            )
        }
        AuthGateState.SignedOut -> LoginRoute()
        is AuthGateState.SignedIn -> SignedInApp()
    }
}

@Composable
private fun SignedInApp(
    offlineBannerViewModel: OfflineBannerViewModel = hiltViewModel(),
    appConfigViewModel: AppConfigViewModel = hiltViewModel(),
) {
    val offlineBannerState by offlineBannerViewModel.state.collectAsStateWithLifecycle()
    CompositionLocalProvider(LocalGlucoseSurfaces provides appConfigViewModel.glucoseSurfaces) {
        MainScaffold(
            offlineBannerState = offlineBannerState,
            navConfig = appConfigViewModel.navConfig,
            flavorNavGraph = appConfigViewModel.flavorNavGraph,
            glucoseSurfaces = appConfigViewModel.glucoseSurfaces,
        )
    }
}

@Composable
fun MainScaffold(
    offlineBannerState: OfflineBannerUiState,
    modifier: Modifier = Modifier,
    navController: NavHostController = rememberNavController(),
    navConfig: NavConfig = DefaultNavConfig,
    flavorNavGraph: FlavorNavGraph = NoopFlavorNavGraph,
    glucoseSurfaces: GlucoseSurfaces = GlucoseSurfacesNoop,
    navHost: (@Composable (Modifier, NavHostController) -> Unit)? = null,
) {
    var captureSheetVisible by remember { mutableStateOf(false) }
    var lastQueuedOutboxId by rememberSaveable { mutableStateOf<String?>(null) }
    var historySearchRequestCounter by rememberSaveable { mutableStateOf(0) }
    val currentBackStack by navController.currentBackStackEntryAsState()
    val fullScreenDetail = currentBackStack?.destination?.route == Route.MealStack.Pattern
    val selectedRoute = currentBackStack?.destination?.route?.toBottomRoute(navConfig) ?: Route.Today.route
    val navigateToTodayWithQueuedOutbox: (String) -> Unit = { outboxId ->
        lastQueuedOutboxId = outboxId
        captureSheetVisible = false
        navController.navigate(Route.Today.route) {
            popUpTo(Route.Today.route) {
                saveState = true
            }
            launchSingleTop = true
            restoreState = true
        }
    }

    Column(
        modifier = modifier
            .fillMaxSize()
            .background(GT.colors.bg)
            .statusBarsPadding(),
    ) {
        GTOfflineBanner(
            state = offlineBannerState,
            onTap = { navController.navigate(Route.OutboxInspector.route) },
        )
        if (!fullScreenDetail) navConfig.brand?.let { brand ->
            GTBrandLockup(
                name = stringResource(brand.name),
                mark = {
                    Image(
                        painter = painterResource(brand.mark),
                        contentDescription = null,
                    )
                },
                rightSlot = {
                    BrandRightSlot(
                        selectedRoute = selectedRoute,
                        hasBrand = true,
                        onHistorySearchClick = { historySearchRequestCounter += 1 },
                    )
                },
            )
        }
        Scaffold(
            containerColor = GT.colors.bg,
            bottomBar = {
                if (!fullScreenDetail) {
                    MainBottomBar(
                        navConfig = navConfig,
                        selectedRoute = selectedRoute,
                        onRouteClick = { route ->
                            navController.navigate(route) {
                                popUpTo(navController.graph.findStartDestination().id) {
                                    saveState = true
                                }
                                launchSingleTop = true
                                restoreState = true
                            }
                        },
                        onCaptureClick = { captureSheetVisible = true },
                        activeIndicatorColor = navConfig.brand?.activeIndicatorColor,
                    )
                }
            },
        ) { innerPadding ->
            val contentModifier = Modifier
                .fillMaxSize()
                .padding(innerPadding)
            if (navHost == null) {
                GTNavHost(
                    navController = navController,
                    lastQueuedOutboxId = lastQueuedOutboxId,
                    onQueuedOutboxConsumed = { consumedId ->
                        if (lastQueuedOutboxId == consumedId) {
                            lastQueuedOutboxId = null
                        }
                    },
                    onOutboxQueued = navigateToTodayWithQueuedOutbox,
                    historySearchRequestCounter = historySearchRequestCounter,
                    navConfig = navConfig,
                    flavorNavGraph = flavorNavGraph,
                    modifier = contentModifier,
                )
            } else {
                CompositionLocalProvider(LocalGlucoseSurfaces provides glucoseSurfaces) {
                    navHost(contentModifier, navController)
                }
            }
        }
    }

    if (captureSheetVisible) {
        GTComposeSheet(
            onDismiss = { captureSheetVisible = false },
            onCameraClick = { navController.navigate(Route.PhotoCapture.route) },
            onOutboxQueued = navigateToTodayWithQueuedOutbox,
        )
    }
}

@Composable
fun GTNavHost(
    navController: NavHostController,
    lastQueuedOutboxId: String? = null,
    onQueuedOutboxConsumed: (String) -> Unit = {},
    onOutboxQueued: (String) -> Unit = {},
    historySearchRequestCounter: Int = 0,
    navConfig: NavConfig = DefaultNavConfig,
    flavorNavGraph: FlavorNavGraph = NoopFlavorNavGraph,
    modifier: Modifier = Modifier,
) {
    val glucoseRoute = navConfig.tabs.firstOrNull { it.icon == NavIcon.Trend }?.route
    val openMealStack: (LocalDate, String) -> Unit = { date, id ->
        navController.navigate(Route.MealStack(date, id).route)
    }
    NavHost(
        navController = navController,
        startDestination = Route.Today.route,
        modifier = modifier,
        enterTransition = { EnterTransition.None },
        exitTransition = { ExitTransition.None },
        popEnterTransition = { EnterTransition.None },
        popExitTransition = { ExitTransition.None },
    ) {
        composable(Route.Today.route) {
            TodayStatsPager(
                onOpenMealStack = openMealStack,
                onOpenOutbox = { id -> navController.navigate(Route.OutboxInspector.focus(id)) },
                onOpenOutboxSummary = { navController.navigate(Route.OutboxInspector.route) },
                lastQueuedOutboxId = lastQueuedOutboxId,
                onQueuedOutboxConsumed = onQueuedOutboxConsumed,
                showPagerKicker = navConfig.brand == null,
                brandAccentColor = navConfig.brand?.activeIndicatorColor,
                onOpenMore = {
                    navController.navigate(Route.More.route) {
                        popUpTo(navController.graph.findStartDestination().id) {
                            saveState = true
                        }
                        launchSingleTop = true
                        restoreState = true
                    }
                },
            )
        }
        composable(
            route = Route.Today.PatternWithDate,
            arguments = listOf(navArgument(Route.Today.ArgDate) { type = NavType.StringType }),
        ) { entry ->
            val initialDate = entry.arguments?.getString(Route.Today.ArgDate)?.let(LocalDate::parse)
            TodayStatsPager(
                onOpenMealStack = openMealStack,
                onOpenOutbox = { id -> navController.navigate(Route.OutboxInspector.focus(id)) },
                onOpenOutboxSummary = { navController.navigate(Route.OutboxInspector.route) },
                lastQueuedOutboxId = lastQueuedOutboxId,
                onQueuedOutboxConsumed = onQueuedOutboxConsumed,
                showPagerKicker = navConfig.brand == null,
                brandAccentColor = navConfig.brand?.activeIndicatorColor,
                initialDate = initialDate,
                onOpenMore = {
                    navController.navigate(Route.More.route) {
                        popUpTo(navController.graph.findStartDestination().id) {
                            saveState = true
                        }
                        launchSingleTop = true
                        restoreState = true
                    }
                },
            )
        }
        with(flavorNavGraph) {
            registerFlavorRoutes(navController)
        }
        composable(Route.History.route) {
            HistoryRoute(
                onOpenMealStack = openMealStack,
                onOpenDay = { date ->
                    navController.navigate(Route.Today.forDate(date)) {
                        popUpTo(Route.Today.route) {
                            saveState = true
                        }
                        launchSingleTop = true
                    }
                },
                searchRequestCounter = historySearchRequestCounter,
                brandAccentColor = navConfig.brand?.activeIndicatorColor,
            )
        }
        composable(
            route = Route.MealStack.Pattern,
            arguments = listOf(
                navArgument(Route.MealStack.ArgDate) { type = NavType.StringType },
                navArgument(Route.MealStack.ArgFocusedId) { type = NavType.StringType },
            ),
            enterTransition = {
                fadeIn(animationSpec = tween(200, easing = LinearOutSlowInEasing))
            },
            popExitTransition = {
                fadeOut(animationSpec = tween(200, easing = LinearOutSlowInEasing))
            },
            exitTransition = {
                fadeOut(animationSpec = tween(200, easing = LinearOutSlowInEasing))
            },
            popEnterTransition = {
                fadeIn(animationSpec = tween(200, easing = LinearOutSlowInEasing))
            },
        ) {
            MealStackRoute(onBack = { navController.popBackStack() })
        }
        composable(Route.Base.route) {
            BaseRoute(
                onOutboxQueued = onOutboxQueued,
            )
        }
        composable(Route.More.route) {
            MoreRoute(
                onOpenBase = {
                    navController.navigate(Route.Base.route) {
                        launchSingleTop = true
                    }
                },
                onOpenOutbox = { navController.navigate(Route.OutboxInspector.route) },
            )
        }
        composable(
            route = Route.OutboxInspector.Pattern,
            arguments = listOf(navArgument(Route.OutboxInspector.ArgId) {
                type = NavType.StringType
                nullable = true
            }),
            deepLinks = listOf(navDeepLink { uriPattern = Route.OutboxInspector.DeepLinkUri }),
        ) { entry ->
            OutboxInspectorRoute(
                focusId = entry.arguments?.getString(Route.OutboxInspector.ArgId),
                onBack = { navController.popBackStack() },
                onOpenJournal = { date ->
                    navController.navigate(Route.Today.forDate(date)) {
                        launchSingleTop = true
                    }
                },
            )
        }
        composable(
            route = Route.Record.Pattern,
            arguments = listOf(navArgument(Route.Record.ArgId) { type = NavType.StringType }),
            enterTransition = { recordEnterTransition() },
            popEnterTransition = { recordEnterTransition() },
            exitTransition = { fadeOut(animationSpec = tween(120)) },
            popExitTransition = { fadeOut(animationSpec = tween(120)) },
        ) { entry ->
            val id = entry.arguments?.getString(Route.Record.ArgId).orEmpty()
            RecordRoute(
                id = id,
                onClose = { navController.popBackStack() },
                onOpenGlucose = {
                    glucoseRoute?.let { route ->
                        navController.navigate(route) {
                            popUpTo(navController.graph.findStartDestination().id) {
                                saveState = true
                            }
                            launchSingleTop = true
                            restoreState = true
                        }
                    }
                },
            )
        }
        composable(Route.PhotoCapture.route) {
            PhotoCaptureScreen(
                onPhotoQueued = { outboxId ->
                    onOutboxQueued(outboxId)
                },
                onClose = { navController.popBackStack() },
            )
        }
    }
}

@Composable
fun GTOfflineBanner(
    state: OfflineBannerUiState,
    onTap: () -> Unit,
    modifier: Modifier = Modifier,
) {
    if (state == OfflineBannerUiState.Hidden) return

    val message = when (state) {
        OfflineBannerUiState.Hidden -> ""
        is OfflineBannerUiState.SyncQueue -> stringResource(R.string.offline_banner_sync_queue, state.queueDepth)
        is OfflineBannerUiState.OfflineStale -> stringResource(R.string.offline_banner_stale, state.dataAt)
        is OfflineBannerUiState.OfflineQueue -> stringResource(R.string.offline_banner_queue, state.queueDepth)
        is OfflineBannerUiState.Stuck -> stringResource(R.string.offline_banner_stuck, state.stuckDepth)
    }
    val tone = when (state) {
        is OfflineBannerUiState.Stuck,
        is OfflineBannerUiState.OfflineQueue,
        is OfflineBannerUiState.OfflineStale,
        -> GT.colors.warn
        else -> GT.colors.muted
    }
    val hairlineColor = GT.colors.hairline
    val hairlineWidth = GT.space.hairline
    val monoStyle = GT.type.monoLabel
    val annotated = buildAnnotatedString {
        append(message)
        if (state is OfflineBannerUiState.OfflineStale) {
            val start = message.indexOf(state.dataAt)
            if (start >= 0) {
                addStyle(
                    SpanStyle(
                        fontFamily = monoStyle.fontFamily,
                        fontSize = monoStyle.fontSize,
                        fontWeight = monoStyle.fontWeight,
                    ),
                    start = start,
                    end = start + state.dataAt.length,
                )
            }
        }
    }

    Box(
        modifier = modifier
            .fillMaxWidth()
            .height(24.dp)
            .background(GT.colors.surface)
            .drawBehind {
                drawLine(
                    color = hairlineColor,
                    start = Offset(0f, size.height),
                    end = Offset(size.width, size.height),
                    strokeWidth = hairlineWidth.toPx(),
                )
            }
            .then(if (state.tappable) Modifier.clickable(onClick = onTap) else Modifier)
            .padding(horizontal = 14.dp),
        contentAlignment = Alignment.CenterStart,
    ) {
        Text(
            text = annotated,
            color = tone,
            style = GT.type.sansLabel,
            maxLines = 1,
        )
    }
}

@Composable
private fun TodayStatsPager(
    onOpenMealStack: (LocalDate, String) -> Unit,
    onOpenOutbox: (String) -> Unit,
    onOpenOutboxSummary: () -> Unit,
    lastQueuedOutboxId: String?,
    onQueuedOutboxConsumed: (String) -> Unit,
    showPagerKicker: Boolean,
    brandAccentColor: Color?,
    initialDate: LocalDate? = null,
    onOpenMore: () -> Unit = {},
) {
    val pagerState = rememberPagerState(pageCount = { 2 })
    val pagerScope = rememberCoroutineScope()
    Column(Modifier.fillMaxSize()) {
        HorizontalPager(
            state = pagerState,
            modifier = Modifier.fillMaxSize(),
        ) { page ->
            when (page) {
                0 -> TodayRoute(
                    onOpenMealStack = onOpenMealStack,
                    onOpenOutbox = onOpenOutbox,
                    onOpenOutboxSummary = onOpenOutboxSummary,
                    lastQueuedOutboxId = lastQueuedOutboxId,
                    onQueuedOutboxConsumed = onQueuedOutboxConsumed,
                    brandAccentColor = brandAccentColor,
                    initialDate = initialDate,
                    showPagerDots = showPagerKicker,
                    pagerPage = pagerState.currentPage,
                    onOpenStats = { pagerScope.launch { pagerState.animateScrollToPage(1) } },
                    onOpenMore = onOpenMore,
                )
                else -> StatsRoute(brandAccentColor = brandAccentColor)
            }
        }
    }
}

@Composable
private fun PlaceholderScreen(title: String) {
    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(18.dp),
    ) {
        Text(
            text = title,
            color = GT.colors.ink,
            style = GT.type.serifTitle,
        )
        GTHintBox(
            text = stringResource(R.string.desktop_only_hint),
            modifier = Modifier.padding(top = 18.dp),
        )
    }
}

@Composable
private fun RecordPlaceholder(id: String) {
    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(18.dp),
    ) {
        Text(
            text = stringResource(R.string.record_title),
            color = GT.colors.ink,
            style = GT.type.serifTitle,
        )
        Text(
            text = id,
            modifier = Modifier.padding(top = 8.dp),
            color = GT.colors.muted,
            style = GT.type.monoLabel,
        )
    }
}

@Composable
private fun MainBottomBar(
    navConfig: NavConfig,
    selectedRoute: String,
    onRouteClick: (String) -> Unit,
    onCaptureClick: () -> Unit,
    activeIndicatorColor: Color?,
) {
    val captureDescription = stringResource(R.string.nav_capture_content_description)
    GTBottomBar(
        items = navConfig.tabs.map { spec ->
            GTBottomBarItem(
                id = spec.route,
                label = stringResource(spec.label),
                selected = selectedRoute == spec.route,
            ) { NavGlyph(spec.icon) }
        },
        onClick = onRouteClick,
        centerSlot = {
            GTFab(
                onClick = onCaptureClick,
                modifier = Modifier
                    .padding(top = 4.dp)
                    .semantics { contentDescription = captureDescription },
            )
        },
        modifier = Modifier.navigationBarsPadding(),
        activeIndicatorColor = activeIndicatorColor ?: GT.colors.ink,
        activeIndicatorUnderIcon = activeIndicatorColor != null,
    )
}

@Composable
private fun BrandRightSlot(
    selectedRoute: String,
    hasBrand: Boolean = false,
    onHistorySearchClick: () -> Unit = {},
) {
    val text = when {
        selectedRoute == Route.Today.route && hasBrand -> null
        selectedRoute == Route.Today.route -> stringResource(R.string.today_stats_action)
        selectedRoute == Route.History.route -> stringResource(R.string.history_search_hint)
        selectedRoute == Route.Base.route -> stringResource(R.string.nav_base)
        selectedRoute == Route.More.route -> stringResource(R.string.nav_more)
        else -> null
    }
    if (text != null) {
        val clickModifier = if (selectedRoute == Route.History.route) {
            Modifier.clickable(onClick = onHistorySearchClick)
        } else {
            Modifier
        }
        Text(
            text = text,
            modifier = clickModifier,
            color = GT.colors.muted,
            style = GT.type.kicker,
            maxLines = 1,
        )
    }
}

private fun String?.toBottomRoute(navConfig: NavConfig): String? =
    when (this) {
        Route.Today.route -> Route.Today.route
        Route.Today.PatternWithDate -> Route.Today.route
        Route.History.route -> Route.History.route
        Route.Base.route -> if (navConfig.tabs.any { it.route == Route.Base.route }) Route.Base.route else Route.More.route
        Route.More.route -> Route.More.route
        else -> navConfig.tabs.firstOrNull { it.route == this }?.route
    }

private fun recordEnterTransition() =
    fadeIn(animationSpec = tween(180)) +
        slideInVertically(
            animationSpec = tween(180),
            initialOffsetY = { 8 },
        )

@Composable
private fun NavGlyph(kind: NavIcon) {
    val color = GT.colors.ink2
    Canvas(modifier = Modifier.size(22.dp)) {
        val stroke = Stroke(width = 1.4.dp.toPx(), cap = StrokeCap.Round)
        when (kind) {
            NavIcon.Today -> {
                drawRoundRect(
                    color = color,
                    topLeft = Offset(4.dp.toPx(), 5.dp.toPx()),
                    size = androidx.compose.ui.geometry.Size(14.dp.toPx(), 13.dp.toPx()),
                    style = stroke,
                )
                drawLine(color, Offset(4.dp.toPx(), 9.dp.toPx()), Offset(18.dp.toPx(), 9.dp.toPx()), stroke.width)
            }
            NavIcon.Trend -> {
                val path = Path().apply {
                    moveTo(2.dp.toPx(), 13.dp.toPx())
                    cubicTo(5.dp.toPx(), 5.dp.toPx(), 9.dp.toPx(), 5.dp.toPx(), 11.dp.toPx(), 12.dp.toPx())
                    cubicTo(13.dp.toPx(), 19.dp.toPx(), 18.dp.toPx(), 16.dp.toPx(), 20.dp.toPx(), 8.dp.toPx())
                }
                drawPath(path = path, color = color, style = stroke)
            }
            NavIcon.History -> {
                drawCircle(
                    color = color,
                    radius = 7.dp.toPx(),
                    center = Offset(11.dp.toPx(), 11.dp.toPx()),
                    style = stroke,
                )
                drawLine(color, Offset(11.dp.toPx(), 7.dp.toPx()), Offset(11.dp.toPx(), 12.dp.toPx()), stroke.width)
                drawLine(color, Offset(11.dp.toPx(), 12.dp.toPx()), Offset(15.dp.toPx(), 14.dp.toPx()), stroke.width)
            }
            NavIcon.Base -> {
                drawRoundRect(
                    color = color,
                    topLeft = Offset(4.dp.toPx(), 5.dp.toPx()),
                    size = androidx.compose.ui.geometry.Size(14.dp.toPx(), 12.dp.toPx()),
                    style = stroke,
                )
                drawLine(color, Offset(7.dp.toPx(), 8.dp.toPx()), Offset(15.dp.toPx(), 8.dp.toPx()), stroke.width)
                drawLine(color, Offset(7.dp.toPx(), 12.dp.toPx()), Offset(15.dp.toPx(), 12.dp.toPx()), stroke.width)
            }
            NavIcon.More -> {
                listOf(6.dp, 11.dp, 16.dp).forEach { x ->
                    drawCircle(
                        color = color,
                        radius = 1.4.dp.toPx(),
                        center = Offset(x.toPx(), 11.dp.toPx()),
                    )
                }
            }
        }
    }
}
