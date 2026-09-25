import java.util.Properties

plugins {
    id("com.android.application")
    // The Flutter Gradle Plugin must be applied after the Android and Kotlin Gradle plugins.
    id("dev.flutter.flutter-gradle-plugin")
}

// Release signing. Provide android/key.properties (never committed) with
// storeFile, storePassword, keyAlias and keyPassword, or the same values as
// FF_KEYSTORE_PATH / FF_KEYSTORE_PASSWORD / FF_KEY_ALIAS / FF_KEY_PASSWORD.
// Without them, release builds are signed with the debug key: fine for
// testing, never for distribution (see docs/RELEASE.md).
val keyProperties = Properties().apply {
    val file = rootProject.file("key.properties")
    if (file.exists()) file.inputStream().use { load(it) }
}
fun signingValue(property: String, env: String): String? =
    keyProperties.getProperty(property) ?: System.getenv(env)
val releaseStoreFile = signingValue("storeFile", "FF_KEYSTORE_PATH")

// AdMob app id: Google's test id unless a real one is passed with
// -PadmobAppId=ca-app-pub-…~… or FF_ADMOB_APP_ID.
val admobAppId: String = (project.findProperty("admobAppId") as String?)
    ?: System.getenv("FF_ADMOB_APP_ID")
    ?: "ca-app-pub-3940256099942544~3347511713"

android {
    namespace = "com.futurefashion.app"
    compileSdk = flutter.compileSdkVersion
    ndkVersion = flutter.ndkVersion

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    buildFeatures {
        resValues = true
    }

    defaultConfig {
        applicationId = "com.futurefashion.app"
        minSdk = maxOf(24, flutter.minSdkVersion)
        targetSdk = flutter.targetSdkVersion
        versionCode = flutter.versionCode
        versionName = flutter.versionName
        manifestPlaceholders["admobAppId"] = admobAppId
    }

    flavorDimensions += "env"
    productFlavors {
        create("dev") {
            dimension = "env"
            applicationIdSuffix = ".dev"
            versionNameSuffix = "-dev"
            resValue("string", "app_name", "Future Fashion Dev")
            manifestPlaceholders["webHost"] = "dev.futurefashion.example"
        }
        create("staging") {
            dimension = "env"
            applicationIdSuffix = ".staging"
            versionNameSuffix = "-staging"
            resValue("string", "app_name", "Future Fashion Staging")
            manifestPlaceholders["webHost"] = "staging.futurefashion.example"
        }
        create("prod") {
            dimension = "env"
            resValue("string", "app_name", "Future Fashion")
            manifestPlaceholders["webHost"] = (project.findProperty("webHost") as String?) ?: "futurefashion.example"
        }
    }

    signingConfigs {
        if (releaseStoreFile != null) {
            create("release") {
                storeFile = file(releaseStoreFile)
                storePassword = signingValue("storePassword", "FF_KEYSTORE_PASSWORD")
                keyAlias = signingValue("keyAlias", "FF_KEY_ALIAS")
                keyPassword = signingValue("keyPassword", "FF_KEY_PASSWORD")
            }
        }
    }

    testOptions {
        unitTests.all { test ->
            // ./gradlew :app:testProdDebugUnitTest -PrealApk=… also checks a real build (ApkReferralTest).
            (project.findProperty("realApk") as String?)?.let { test.systemProperty("ff.realApk", it) }
        }
    }

    buildTypes {
        release {
            signingConfig = if (releaseStoreFile != null) {
                signingConfigs.getByName("release")
            } else {
                logger.warn("No release keystore configured: signing with the debug key (not for distribution).")
                signingConfigs.getByName("debug")
            }
        }
    }
}

kotlin {
    compilerOptions {
        jvmTarget = org.jetbrains.kotlin.gradle.dsl.JvmTarget.JVM_17
    }
}

flutter {
    source = "../.."
}

dependencies {
    testImplementation("junit:junit:4.13.2")
    testImplementation("com.android.tools.build:apksig:8.13.1")
}
