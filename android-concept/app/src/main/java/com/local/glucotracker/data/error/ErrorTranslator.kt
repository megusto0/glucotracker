package com.local.glucotracker.data.error

import com.local.glucotracker.data.sync.OutboxHttpException
import com.local.glucotracker.domain.model.UserError
import io.ktor.client.plugins.HttpRequestTimeoutException
import io.ktor.client.plugins.ResponseException
import java.net.ConnectException
import java.net.NoRouteToHostException
import java.net.SocketTimeoutException
import java.net.UnknownHostException
import javax.inject.Inject
import kotlinx.coroutines.CancellationException

class ErrorTranslator @Inject constructor() {
    fun translate(t: Throwable): UserError = when {
        t is CancellationException ->
            error("CancellationException must not be translated; handle it at the call site")
        t is HttpRequestTimeoutException || t is SocketTimeoutException -> serverUnreachable
        t is UnknownHostException || t is NoRouteToHostException -> noNetwork
        t is ConnectException -> serverUnreachable
        t is OutboxHttpException && t.status == 401 -> authLost
        t is OutboxHttpException && t.status in 400..499 -> requestRejected
        t is OutboxHttpException && t.status in 500..599 -> serverError
        t is ResponseException && t.response.status.value == 401 -> authLost
        t is ResponseException && t.response.status.value in 400..499 -> requestRejected
        t is ResponseException && t.response.status.value in 500..599 -> serverError
        else -> unknown
    }

    private val serverUnreachable = UserError(
        code = "server_unreachable",
        message = "сервер не отвечает · повторим автоматически",
        severity = UserError.Severity.Warn,
        retryable = true,
    )

    private val noNetwork = UserError(
        code = "no_network",
        message = "нет соединения · подключись к сети",
        severity = UserError.Severity.Warn,
        retryable = true,
    )

    private val authLost = UserError(
        code = "auth_lost",
        message = "нужно войти заново",
        severity = UserError.Severity.Error,
        retryable = false,
    )

    private val requestRejected = UserError(
        code = "request_rejected",
        message = "сервер не принял запись",
        severity = UserError.Severity.Warn,
        retryable = false,
    )

    private val serverError = UserError(
        code = "server_error",
        message = "ошибка на сервере · повторим автоматически",
        severity = UserError.Severity.Warn,
        retryable = true,
    )

    private val unknown = UserError(
        code = "unknown",
        message = "что-то пошло не так · повторить",
        severity = UserError.Severity.Error,
        retryable = true,
    )
}
