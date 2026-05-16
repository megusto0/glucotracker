package com.local.glucotracker.data.error

import com.local.glucotracker.data.sync.OutboxHttpException
import java.net.ConnectException
import java.net.NoRouteToHostException
import java.net.SocketTimeoutException
import java.net.UnknownHostException
import kotlinx.coroutines.CancellationException
import org.junit.Assert.assertEquals
import org.junit.Assert.fail
import org.junit.Test

class ErrorTranslatorTest {
    private val translator = ErrorTranslator()

    @Test
    fun mapsTimeoutsToServerUnreachable() {
        val error = translator.translate(SocketTimeoutException("raw timeout"))

        assertEquals("server_unreachable", error.code)
        assertEquals("сервер не отвечает · повторим автоматически", error.message)
    }

    @Test
    fun mapsNetworkLookupFailuresToNoNetwork() {
        assertEquals("no_network", translator.translate(UnknownHostException("host")).code)
        assertEquals("no_network", translator.translate(NoRouteToHostException("route")).code)
    }

    @Test
    fun mapsConnectFailureToServerUnreachable() {
        assertEquals("server_unreachable", translator.translate(ConnectException("refused")).code)
    }

    @Test
    fun mapsHttpStatuses() {
        assertEquals("auth_lost", translator.translate(OutboxHttpException(401, "HTTP 401")).code)
        assertEquals("request_rejected", translator.translate(OutboxHttpException(422, "HTTP 422")).code)
        assertEquals("server_error", translator.translate(OutboxHttpException(503, "HTTP 503")).code)
    }

    @Test
    fun mapsUnknownErrorsWithoutPassingRawMessageThrough() {
        val error = translator.translate(IllegalStateException("Connect timeout has expired [url=http://192.168.3.6]"))

        assertEquals("unknown", error.code)
        assertEquals("что-то пошло не так · повторить", error.message)
    }

    @Test
    fun refusesToTranslateCancellation() {
        try {
            translator.translate(CancellationException("Job was cancelled"))
            fail("CancellationException should not be translated")
        } catch (_: IllegalStateException) {
            // Expected: cancellation must be handled by the caller.
        }
    }
}
