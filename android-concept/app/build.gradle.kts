import java.io.ByteArrayOutputStream
import java.nio.charset.StandardCharsets
import java.util.zip.ZipFile

plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.android)
    alias(libs.plugins.kotlin.kapt)
    alias(libs.plugins.kotlin.compose)
    alias(libs.plugins.kotlin.serialization)
    alias(libs.plugins.hilt)
    alias(libs.plugins.paparazzi)
}

val openApiGenerator by configurations.creating
val openApiSpec = rootProject.layout.projectDirectory.file("../docs/openapi.yaml")
val openApiSpecPath = openApiSpec.asFile.absolutePath.replace('\\', '/')
val generatedOpenApiDir = layout.buildDirectory.dir("generated/openapi")
val generatedOpenApiKotlinDir = generatedOpenApiDir.map { it.dir("src/main/kotlin") }
val generatedFoodOpenApiKotlinDir = layout.buildDirectory.dir("generated/openapi-food/src/main/kotlin")
val debugApiBaseUrl = providers.gradleProperty("glucotracker.debugApiBaseUrl")
    .orElse(providers.environmentVariable("GLUCOTRACKER_DEBUG_API_BASE_URL"))
    .orElse("https://megusto.duckdns.org:1338")

android {
    namespace = "com.local.glucotracker"
    compileSdk = 35

    defaultConfig {
        applicationId = "com.glucotracker.mobile"
        minSdk = 26
        targetSdk = 35
        versionCode = 1
        versionName = "0.1.0"

        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
    }

    flavorDimensions += "edition"
    productFlavors {
        create("gluco") {
            dimension = "edition"
        }
        create("food") {
            dimension = "edition"
            applicationIdSuffix = ".food"
            versionNameSuffix = "-food"
        }
    }

    buildTypes {
        debug {
            isMinifyEnabled = false
            buildConfigField(
                "String",
                "API_BASE_URL",
                "\"${debugApiBaseUrl.get()}\"",
            )
        }
        release {
            isMinifyEnabled = true
            buildConfigField(
                "String",
                "API_BASE_URL",
                "\"https://megusto.duckdns.org:1338\"",
            )
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro",
            )
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlinOptions {
        jvmTarget = "17"
    }

    buildFeatures {
        compose = true
        buildConfig = true
    }

    sourceSets {
        getByName("gluco") {
            java.srcDir("src/gluco/java")
            java.srcDir(generatedOpenApiKotlinDir)
            res.srcDir("src/gluco/res")
        }
        getByName("food") {
            java.srcDir("src/food/java")
            java.srcDir(generatedFoodOpenApiKotlinDir)
            res.srcDir("src/food/res")
        }
    }

    lint {
        abortOnError = true
        warningsAsErrors = false
    }
}

kapt {
    correctErrorTypes = true
}

tasks.register<JavaExec>("generateApiClient") {
    group = "code generation"
    description = "Generate the Kotlin/Ktor OpenAPI client from docs/openapi.yaml."

    classpath = openApiGenerator
    mainClass.set("org.openapitools.codegen.OpenAPIGenerator")
    args(
        "generate",
        "-g",
        "kotlin",
        "-i",
        openApiSpecPath,
        "-o",
        generatedOpenApiDir.get().asFile.absolutePath,
        "--library",
        "jvm-ktor",
        "--package-name",
        "com.local.glucotracker.generated",
        "--api-package",
        "com.local.glucotracker.generated.api",
        "--model-package",
        "com.local.glucotracker.generated.model",
        "--additional-properties",
        listOf(
            "serializationLibrary=kotlinx_serialization",
            "dateLibrary=kotlinx-datetime",
            "collectionType=list",
            "enumPropertyNaming=UPPERCASE",
        ).joinToString(","),
    )

    inputs.file(openApiSpec)
    outputs.dir(generatedOpenApiDir)

    doLast {
        val generatedRoot = generatedOpenApiKotlinDir.get().asFile
        generatedRoot.walkTopDown()
            .filter { it.isFile && it.extension == "kt" }
            .forEach { file ->
                var text = file.readText()
                text = text
                    .replace(
                        "kotlin.collections.List<@Contextual kotlin.Any>",
                        "kotlin.collections.List<kotlinx.serialization.json.JsonElement>",
                    )
                    .replace(
                        "kotlin.collections.Map<kotlin.String, kotlin.Any>",
                        "kotlin.collections.Map<kotlin.String, kotlinx.serialization.json.JsonElement>",
                    )
                    .replace(
                        "authorization: kotlin.String?",
                        "authorization: kotlin.String? = null",
                    )
                    .replace(
                        "append(\"idempotency_key\", idempotencyKey)",
                        "append(\"idempotency_key\", idempotencyKey.toString())",
                    )

                if (file.name == "DashboardApi.kt") {
                    text = text
                        .replace(
                            "import com.local.glucotracker.generated.model.ResponseGetdashboardtoday\n",
                            "import com.local.glucotracker.generated.model.DashboardTodayResponse\n",
                        )
                        .replace(
                            "HttpResponse<ResponseGetdashboardtoday>",
                            "HttpResponse<DashboardTodayResponse>",
                        )
                        .replace(
                            "ResponseGetdashboardtoday",
                            "DashboardTodayResponse",
                        )
                }

                if (file.name == "NightscoutApi.kt") {
                    text = text
                        .replace(
                            "import com.local.glucotracker.generated.model.ResponseGettimeline\n",
                            "import com.local.glucotracker.generated.model.ResponseGettimeline\n" +
                                "import com.local.glucotracker.generated.model.TimelineResponse\n",
                        )
                        .replace(
                            "HttpResponse<ResponseGettimeline>",
                            "HttpResponse<TimelineResponse>",
                        )
                }

                if (file.name == "ApiClient.kt") {
                    text = text
                        .replace(
                            "import io.ktor.client.plugins.contentnegotiation.ContentNegotiation\n",
                            "import io.ktor.client.plugins.contentnegotiation.ContentNegotiation\n" +
                                "import io.ktor.serialization.kotlinx.json.json\n" +
                                "import com.local.glucotracker.data.api.OpenApiJson\n",
                        )
                        .replace(
                            "it.install(ContentNegotiation) {\n            }\n",
                            "it.install(ContentNegotiation) {\n                json(OpenApiJson.json)\n            }\n",
                        )
                }

                file.writeText(text)
            }

        val foodRoot = generatedFoodOpenApiKotlinDir.get().asFile
        delete(foodRoot)
        copy {
            from(generatedRoot)
            into(foodRoot)
        }
        val bannedClassTerms = listOf(
            "Glucose",
            "Nightscout",
            "Cgm",
            "Fingerstick",
            "Tir",
            "Endocrinologist",
            "HealthConnect",
        )
        val ktFiles = foodRoot.walkTopDown()
            .filter { it.isFile && it.extension == "kt" }
            .toList()
        val removedSimpleNames = mutableSetOf<String>()
        var changed: Boolean
        do {
            changed = false
            ktFiles
                .filter { it.exists() }
                .forEach { file ->
                    val simpleName = file.nameWithoutExtension
                    val text = file.readText()
                    val shouldRemove = bannedClassTerms.any { term -> simpleName.contains(term) } ||
                        removedSimpleNames.any { removed -> text.contains(removed) }
                    if (shouldRemove && removedSimpleNames.add(simpleName)) {
                        changed = true
                    }
                }
        } while (changed)
        ktFiles
            .filter { it.nameWithoutExtension in removedSimpleNames }
            .forEach { it.delete() }
    }
}

tasks.named("preBuild") {
    dependsOn("generateApiClient")
}

val foodClassBannedTerms = listOf(
    "Glucose",
    "Nightscout",
    "Cgm",
    "Fingerstick",
    "Tir",
    "Endocrinologist",
    "HealthConnect",
)
val allowedFoodClassPrefixes = listOf(
    "com/local/glucotracker/ui/glucose/",
)

tasks.register("verifyFoodDebugNoGlucoseClasses") {
    group = "verification"
    description = "Fail if the food debug variant contains glucose-related class names outside shared no-op surface contracts."
    doLast {
        val classDirs = listOf(
            layout.buildDirectory.dir("tmp/kotlin-classes/foodDebug").get().asFile,
            layout.buildDirectory.dir("intermediates/javac/foodDebug/classes").get().asFile,
        )
        val offenders = classDirs
            .filter { it.exists() }
            .flatMap { root ->
                root.walkTopDown()
                    .filter { it.isFile && it.extension == "class" }
                    .map { file -> file.relativeTo(root).invariantSeparatorsPath.removeSuffix(".class") }
                    .filter { className ->
                        foodClassBannedTerms.any { term -> className.contains(term) } &&
                            allowedFoodClassPrefixes.none { prefix -> className.startsWith(prefix) }
                    }
                    .toList()
            }
            .distinct()
            .sorted()
        if (offenders.isNotEmpty()) {
            throw GradleException(
                "Food APK contains glucose-related classes:\n" + offenders.joinToString("\n"),
            )
        }
    }
}

tasks.register("verifyTarelkaColorScope") {
    group = "verification"
    description = "Fail if the Tarelka accent color leaks outside the food flavor source set."
    doLast {
        val forbidden = listOf(
            "0xFFD" + "97E4A",
            "#D" + "97E4A",
            "tanger" + "ine",
        )
        val scannedRoots = listOf(
            layout.projectDirectory.dir("src/main").asFile,
            layout.projectDirectory.dir("src/gluco").asFile,
        )
        val offenders = scannedRoots
            .filter { it.exists() }
            .flatMap { root ->
                root.walkTopDown()
                    .filter { it.isFile }
                    .filter { file ->
                        val text = file.readText()
                        forbidden.any { term -> text.contains(term, ignoreCase = true) }
                    }
                    .map { it.relativeTo(layout.projectDirectory.asFile).invariantSeparatorsPath }
                    .toList()
            }
        if (offenders.isNotEmpty()) {
            throw GradleException(
                "Tarelka accent color leaked outside src/food:\n" + offenders.joinToString("\n"),
            )
        }
    }
}

fun ByteArray.readUIntLe(offset: Int): Int =
    (this[offset].toInt() and 0xff) or
        ((this[offset + 1].toInt() and 0xff) shl 8) or
        ((this[offset + 2].toInt() and 0xff) shl 16) or
        ((this[offset + 3].toInt() and 0xff) shl 24)

fun ByteArray.readUleb128(offset: Int): Pair<Int, Int> {
    var result = 0
    var shift = 0
    var index = offset
    while (true) {
        val current = this[index].toInt() and 0xff
        result = result or ((current and 0x7f) shl shift)
        index += 1
        if ((current and 0x80) == 0) return result to index
        shift += 7
    }
}

fun ByteArray.dexStrings(): List<String> {
    if (size < 112 || !String(this, 0, 3, StandardCharsets.US_ASCII).startsWith("dex")) {
        return emptyList()
    }
    val stringIdsSize = readUIntLe(56)
    val stringIdsOff = readUIntLe(60)
    return (0 until stringIdsSize).map { index ->
        val stringDataOff = readUIntLe(stringIdsOff + index * 4)
        val stringStart = readUleb128(stringDataOff).second
        var end = stringStart
        while (end < size && this[end].toInt() != 0) end += 1
        String(this, stringStart, end - stringStart, StandardCharsets.UTF_8)
    }
}

fun ByteArray.dexClassFqns(): List<String> {
    if (size < 112 || !String(this, 0, 3, StandardCharsets.US_ASCII).startsWith("dex")) {
        return emptyList()
    }
    val strings = dexStrings()
    val typeIdsSize = readUIntLe(64)
    val typeIdsOff = readUIntLe(68)
    return (0 until typeIdsSize).mapNotNull { index ->
        val descriptorIndex = readUIntLe(typeIdsOff + index * 4)
        val descriptor = strings.getOrNull(descriptorIndex) ?: return@mapNotNull null
        descriptor
            .takeIf { it.startsWith("L") && it.endsWith(";") }
            ?.removePrefix("L")
            ?.removeSuffix(";")
            ?.replace('/', '.')
    }
}

fun latestAapt2(): File {
    val executable = if (System.getProperty("os.name").startsWith("Windows")) "aapt2.exe" else "aapt2"
    return android.sdkDirectory.resolve("build-tools")
        .listFiles()
        .orEmpty()
        .map { it.resolve(executable) }
        .filter { it.isFile }
        .maxByOrNull { it.parentFile.name }
        ?: throw GradleException("Could not find $executable under ${android.sdkDirectory}/build-tools.")
}

fun dumpApkResources(apk: File): String {
    val output = ByteArrayOutputStream()
    val errors = ByteArrayOutputStream()
    val result = exec {
        commandLine(latestAapt2().absolutePath, "dump", "resources", apk.absolutePath)
        standardOutput = output
        errorOutput = errors
        isIgnoreExitValue = true
    }
    if (result.exitValue != 0) {
        throw GradleException(
            "aapt2 dump resources failed for ${apk.absolutePath}:\n" +
                errors.toString(StandardCharsets.UTF_8.name()),
        )
    }
    return output.toString(StandardCharsets.UTF_8.name())
}

tasks.register("verifyFoodHasNoGlucose") {
    group = "verification"
    description = "Fail if the packaged food release APK exposes glucose classes or resource copy."
    dependsOn("packageFoodRelease")

    val apkDir = layout.buildDirectory.dir("outputs/apk/food/release")
    inputs.dir(apkDir)

    doLast {
        val apk = apkDir.get().asFile
            .listFiles { file -> file.isFile && file.extension == "apk" }
            .orEmpty()
            .sortedBy { it.name }
            .firstOrNull()
            ?: throw GradleException("Food release APK not found in ${apkDir.get().asFile}.")

        val classBannedTerms = listOf("glucose", "nightscout", "cgm", "fingerstick", "tir", "daypart")
        val appClassPrefixes = listOf(
            "com.local.glucotracker.",
            "com.glucotracker.",
        )
        val allowedNoopClassPrefixes = listOf(
            "com.local.glucotracker.ui.glucose.",
        )
        val stringBannedTerms = listOf("глюкоза", "инсулин", "nightscout", "сенсор")
        val stringBannedTokenRegexes = listOf("cgm").map { token ->
            Regex("(^|[^a-z0-9])${Regex.escape(token)}([^a-z0-9]|$)", RegexOption.IGNORE_CASE)
        }

        val classOffenders = ZipFile(apk).use { zip ->
            zip.entries().asSequence()
                .filter { !it.isDirectory && it.name.matches(Regex("classes\\d*\\.dex")) }
                .flatMap { entry ->
                    zip.getInputStream(entry).use { stream ->
                        stream.readBytes().dexClassFqns().asSequence()
                    }
                }
                .filter { className ->
                    val normalized = className.lowercase()
                    appClassPrefixes.any { prefix -> className.startsWith(prefix) } &&
                        allowedNoopClassPrefixes.none { prefix -> className.startsWith(prefix) } &&
                        classBannedTerms.any { it in normalized }
                }
                .distinct()
                .sorted()
                .toList()
        }

        val resourceDump = dumpApkResources(apk)
        val resourceOffenders = resourceDump
            .lineSequence()
            .filter { line ->
                val normalized = line.lowercase()
                stringBannedTerms.any { it in normalized } ||
                    stringBannedTokenRegexes.any { it.containsMatchIn(normalized) }
            }
            .distinct()
            .take(50)
            .toList()

        val failures = buildList {
            if (classOffenders.isNotEmpty()) {
                add(
                    "Food release APK contains glucose-related class FQNs:\n" +
                        classOffenders.joinToString("\n"),
                )
            }
            if (resourceOffenders.isNotEmpty()) {
                add(
                    "Food release APK contains glucose-related resource strings:\n" +
                        resourceOffenders.joinToString("\n"),
                )
            }
        }

        if (failures.isNotEmpty()) {
            throw GradleException(failures.joinToString("\n\n"))
        }
    }
}

afterEvaluate {
    tasks.named("assembleFoodDebug") {
        finalizedBy("verifyFoodDebugNoGlucoseClasses", "verifyTarelkaColorScope")
    }
    tasks.named("assembleFoodRelease") {
        finalizedBy("verifyFoodHasNoGlucose")
    }
    tasks.named("check") {
        dependsOn("verifyFoodHasNoGlucose")
    }
}

dependencies {
    openApiGenerator(libs.openapi.generator.cli)

    implementation(libs.core.ktx)
    implementation(libs.activity.compose)
    implementation(libs.navigation.compose)
    implementation(libs.hilt.navigation.compose)
    implementation(libs.lifecycle.viewmodel.ktx)
    implementation(libs.lifecycle.runtime.compose)
    implementation(libs.startup.runtime)
    "glucoImplementation"(libs.health.connect.client)
    implementation(libs.guava.android)

    implementation(platform(libs.compose.bom))
    implementation(libs.compose.ui)
    implementation(libs.compose.ui.graphics)
    implementation(libs.compose.ui.tooling.preview)
    implementation(libs.compose.material3)

    implementation(libs.hilt.android)
    kapt(libs.hilt.compiler)

    implementation(libs.security.crypto)

    implementation(libs.ktor.core)
    implementation(libs.ktor.content.negotiation)
    implementation(libs.ktor.serialization.json)
    implementation(libs.ktor.logging)
    implementation(libs.ktor.android)
    implementation(libs.ktor.auth)

    implementation(libs.kotlinx.serialization.json)

    implementation(libs.room.runtime)
    implementation(libs.room.ktx)
    kapt(libs.room.compiler)

    implementation(libs.datastore)
    implementation(libs.datastore.preferences)

    implementation(libs.workmanager)

    implementation(libs.camerax.core)
    implementation(libs.camerax.camera2)
    implementation(libs.camerax.lifecycle)
    implementation(libs.camerax.view)

    implementation(libs.coil.compose)
    implementation(libs.coil.network.ktor)

    implementation(libs.kotlinx.datetime)

    debugImplementation(libs.compose.ui.tooling)
    debugImplementation(libs.compose.ui.test.manifest)

    testImplementation(platform(libs.compose.bom))
    testImplementation(libs.junit)
    testImplementation(libs.turbine)
    testImplementation(libs.coroutines.test)
    testImplementation(libs.ktor.mock)
    testImplementation(libs.compose.ui.test.junit4)

    androidTestImplementation(platform(libs.compose.bom))
    androidTestImplementation(libs.androidx.test.ext)
    androidTestImplementation(libs.androidx.test.runner)
    androidTestImplementation(libs.coroutines.test)
    androidTestImplementation(libs.turbine)
    androidTestImplementation(libs.compose.ui.test.junit4)
}
