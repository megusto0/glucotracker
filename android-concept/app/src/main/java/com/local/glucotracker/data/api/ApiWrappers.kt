package com.local.glucotracker.data.api

import com.local.glucotracker.generated.api.ActivityApi as GeneratedActivityApi
import com.local.glucotracker.generated.api.DashboardApi as GeneratedDashboardApi
import com.local.glucotracker.generated.api.DatabaseApi as GeneratedDatabaseApi
import com.local.glucotracker.generated.api.MealsApi as GeneratedMealsApi
import com.local.glucotracker.generated.api.PatternsApi as GeneratedPatternsApi
import com.local.glucotracker.generated.api.ProductsApi as GeneratedProductsApi
import com.local.glucotracker.generated.api.ScheduleApi as GeneratedScheduleApi
import com.local.glucotracker.generated.api.StatsApi as GeneratedStatsApi
import com.local.glucotracker.generated.api.UsersApi as GeneratedUsersApi
import com.local.glucotracker.generated.model.ActivitySyncRequest
import com.local.glucotracker.generated.model.ActivitySyncResponse
import com.local.glucotracker.generated.model.DashboardDayResponse
import com.local.glucotracker.generated.model.DashboardRangeResponse
import com.local.glucotracker.generated.model.DashboardTodayResponse
import com.local.glucotracker.generated.model.DatabaseItemResponse
import com.local.glucotracker.generated.model.KcalBalanceRangeResponse
import com.local.glucotracker.generated.model.KcalBalanceResponse
import com.local.glucotracker.generated.model.MealResponse
import com.local.glucotracker.generated.model.MealStatus
import com.local.glucotracker.generated.model.PatternResponse
import com.local.glucotracker.generated.model.ProductResponse
import com.local.glucotracker.generated.model.ScheduleOverrideRequest
import com.local.glucotracker.generated.model.ScheduleResponse
import com.local.glucotracker.generated.model.StatsInsightResponse
import com.local.glucotracker.generated.model.StatsOverviewResponse
import com.local.glucotracker.generated.model.UserGoalsUpdate as GeneratedUserGoalsUpdate
import javax.inject.Inject
import kotlinx.datetime.DatePeriod
import kotlinx.datetime.Instant
import kotlinx.datetime.LocalDate
import kotlinx.datetime.TimeZone
import kotlinx.datetime.atStartOfDayIn
import kotlinx.datetime.plus
import kotlinx.datetime.toLocalDateTime

private const val ApiPageLimit = 100

private suspend fun <Page, Item> fetchPaged(
    requestedLimit: Int,
    requestedOffset: Int = 0,
    fetch: suspend (limit: Int, offset: Int) -> Page,
    pageItems: (Page) -> List<Item>,
    pageTotal: (Page) -> Int,
): List<Item> {
    if (requestedLimit <= 0) return emptyList()

    val results = mutableListOf<Item>()
    var offset = requestedOffset.coerceAtLeast(0)
    var remaining = requestedLimit

    while (remaining > 0) {
        val pageLimit = minOf(ApiPageLimit, remaining)
        val page = fetch(pageLimit, offset)
        val items = pageItems(page)

        if (items.isEmpty()) break

        results += items
        offset += items.size
        remaining -= items.size

        if (results.size >= requestedLimit || offset >= pageTotal(page) || items.size < pageLimit) {
            break
        }
    }

    return results
}

class TodayApi @Inject constructor(
    private val dashboardApi: GeneratedDashboardApi,
) {
    suspend fun getToday(): DashboardTodayResponse =
        dashboardApi.getDashboardToday().body()

    suspend fun getDay(date: LocalDate): DashboardDayResponse? =
        dashboardApi.getDashboardRange(from = date, to = date).body().days.firstOrNull()
}

class MealApi @Inject constructor(
    private val mealsApi: GeneratedMealsApi,
) {
    suspend fun listMeals(
        from: Instant?,
        to: Instant?,
        limit: Int = 200,
        offset: Int = 0,
        q: String? = null,
        status: MealStatus? = null,
        tag: String? = null,
        sweet: Boolean? = null,
        breakfast: Boolean? = null,
        photoOnly: Boolean? = null,
        lowConfidence: Boolean? = null,
    ): List<MealResponse> =
        fetchPaged(
            requestedLimit = limit,
            requestedOffset = offset,
            fetch = { pageLimit, pageOffset ->
                mealsApi.listMeals(
                    from = from,
                    to = to,
                    limit = pageLimit,
                    offset = pageOffset,
                    q = q,
                    status = status,
                    tag = tag,
                    sweet = sweet,
                    breakfast = breakfast,
                    photoOnly = photoOnly,
                    lowConfidence = lowConfidence,
                    idempotencyKey = null,
                ).body()
            },
            pageItems = { it.items },
            pageTotal = { it.total },
        )

    suspend fun listMealsForLocalDays(
        fromDay: LocalDate,
        toDay: LocalDate,
        limit: Int = 500,
        q: String? = null,
        status: MealStatus? = null,
        tag: String? = null,
        sweet: Boolean? = null,
        breakfast: Boolean? = null,
        photoOnly: Boolean? = null,
        lowConfidence: Boolean? = null,
    ): List<MealResponse> {
        val networkLimit = (limit + ApiPageLimit * 2).coerceAtMost(1_000)
        return listMeals(
            from = fromDay.plus(DatePeriod(days = -1)).startOfDay(),
            to = toDay.plus(DatePeriod(days = 2)).startOfDay(),
            limit = networkLimit,
            q = q,
            status = status,
            tag = tag,
            sweet = sweet,
            breakfast = breakfast,
            photoOnly = photoOnly,
            lowConfidence = lowConfidence,
        ).filter { meal ->
            val day = meal.eatenAt.toLocalDateTime(TimeZone.currentSystemDefault()).date
            day >= fromDay && day <= toDay
        }.take(limit)
    }

    suspend fun getMeal(id: java.util.UUID): MealResponse =
        mealsApi.getMeal(id).body()

    /** Promote a confirmed meal item into the product DB (quick-add / favorite). */
    suspend fun rememberProduct(
        itemId: java.util.UUID,
        aliases: List<String>? = null,
    ): com.local.glucotracker.generated.model.ProductResponse =
        mealsApi.rememberProductFromMealItem(
            itemId = itemId,
            rememberProductRequest = com.local.glucotracker.generated.model
                .RememberProductRequest(aliases = aliases),
        ).body()

    suspend fun getByIdempotencyKey(key: String): MealResponse? {
        val page = mealsApi.listMeals(
            from = null,
            to = null,
            limit = 1,
            offset = 0,
            q = null,
            status = null,
            tag = null,
            sweet = null,
            breakfast = null,
            photoOnly = null,
            lowConfidence = null,
            idempotencyKey = key,
        ).body()
        return page.items.firstOrNull()
    }
}

private fun LocalDate.startOfDay(): Instant =
    atStartOfDayIn(TimeZone.currentSystemDefault())

class StatsApi @Inject constructor(
    private val activityApi: GeneratedActivityApi,
    private val statsApi: GeneratedStatsApi,
) {
    suspend fun kcalBalance(day: LocalDate): KcalBalanceResponse =
        activityApi.getKcalBalance(day).body()

    suspend fun insights(period: String, slot: String): List<StatsInsightResponse> =
        statsApi.getStatsInsights(period = period, slot = slot).body().insights

    suspend fun overview(period: String): StatsOverviewResponse =
        statsApi.getStatsOverview(period = period).body()
}

class ScheduleApi @Inject constructor(
    private val scheduleApi: GeneratedScheduleApi,
) {
    suspend fun getSchedule(): ScheduleResponse =
        scheduleApi.getMySchedule().body()

    suspend fun setOverride(anchorMinutes: Int): ScheduleResponse =
        scheduleApi.putMyScheduleOverride(
            ScheduleOverrideRequest(anchorMinutes = anchorMinutes),
        ).body()

    suspend fun clearOverride(): ScheduleResponse =
        scheduleApi.deleteMyScheduleOverride().body()
}

class HistoryApi @Inject constructor(
    private val dashboardApi: GeneratedDashboardApi,
    private val activityApi: GeneratedActivityApi,
    private val mealApi: MealApi,
) {
    suspend fun dashboardRange(from: LocalDate, to: LocalDate): DashboardRangeResponse =
        dashboardApi.getDashboardRange(from = from, to = to).body()

    suspend fun balanceRange(from: LocalDate, to: LocalDate): KcalBalanceRangeResponse =
        activityApi.getKcalBalanceRange(fromDate = from, toDate = to).body()

    suspend fun meals(from: Instant, to: Instant): List<MealResponse> =
        mealApi.listMeals(from = from, to = to)

    suspend fun search(
        query: String,
        from: Instant,
        to: Instant,
        status: MealStatus?,
        limit: Int = 100,
    ): List<MealResponse> =
        mealApi.listMeals(
            from = from,
            to = to,
            limit = limit,
            offset = 0,
            q = query,
            status = status,
            tag = null,
        )
}

class ProductsApi @Inject constructor(
    private val productsApi: GeneratedProductsApi,
    private val patternsApi: GeneratedPatternsApi,
    private val databaseApi: GeneratedDatabaseApi,
) {
    suspend fun products(limit: Int = 500): List<ProductResponse> =
        fetchPaged(
            requestedLimit = limit,
            fetch = { pageLimit, pageOffset ->
                productsApi.listProducts(q = null, limit = pageLimit, offset = pageOffset).body()
            },
            pageItems = { it.items },
            pageTotal = { it.total },
        )

    suspend fun templates(limit: Int = 500): List<PatternResponse> =
        fetchPaged(
            requestedLimit = limit,
            fetch = { pageLimit, pageOffset ->
                patternsApi.listPatterns(limit = pageLimit, offset = pageOffset).body()
            },
            pageItems = { it.items },
            pageTotal = { it.total },
        )

    suspend fun databaseItems(limit: Int = 500): List<DatabaseItemResponse> =
        fetchPaged(
            requestedLimit = limit,
            fetch = { pageLimit, pageOffset ->
                databaseApi.listDatabaseItems(
                    type = null,
                    source = null,
                    q = null,
                    needsReview = null,
                    limit = pageLimit,
                    offset = pageOffset,
                ).body()
            },
            pageItems = { it.items },
            pageTotal = { it.total },
        )
}

class SyncApi @Inject constructor(
    private val activityApi: GeneratedActivityApi,
) {
    suspend fun syncActivity(request: ActivitySyncRequest): ActivitySyncResponse =
        activityApi.syncActivity(request).body()
}

class GoalsApi @Inject constructor(
    private val usersApi: GeneratedUsersApi,
) {
    suspend fun getGoals(): com.local.glucotracker.generated.model.UserGoalsResponse =
        usersApi.getMyGoals().body()

    suspend fun updateGoals(
        kcalGoalPerDay: Int?,
        proteinGoalGPerDay: Int?,
        carbGoalGPerDay: Int?,
        fatGoalGPerDay: Int?,
        goalsSetupCompleted: Boolean?,
    ): com.local.glucotracker.generated.model.UserGoalsResponse =
        usersApi.updateMyGoals(
            GeneratedUserGoalsUpdate(
                kcalGoalPerDay = kcalGoalPerDay,
                proteinGoalGPerDay = proteinGoalGPerDay,
                carbGoalGPerDay = carbGoalGPerDay,
                fatGoalGPerDay = fatGoalGPerDay,
                goalsSetupCompleted = goalsSetupCompleted,
            ),
        ).body()
}
