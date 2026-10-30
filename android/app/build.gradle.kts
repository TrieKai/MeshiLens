plugins {
    id("com.android.application")
}

android {
    namespace = "com.meshilens.android"
    compileSdk = 36

    defaultConfig {
        applicationId = "com.meshilens.android"
        minSdk = 26
        targetSdk = 36
        // Same release as extension/manifest.json; versionCode is major * 10000 + minor * 100 + patch.
        versionCode = 608
        versionName = "0.6.8"
    }

    buildTypes {
        release {
            isMinifyEnabled = false
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    testOptions {
        unitTests.isReturnDefaultValues = true
    }
}

dependencies {
    testImplementation("junit:junit:4.13.2")
    // android.jar only ships org.json stubs; JVM unit tests need the real parser.
    testImplementation("org.json:json:20260814")
}
