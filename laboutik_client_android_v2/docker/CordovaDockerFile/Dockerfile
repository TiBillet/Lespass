FROM debian:12-slim

# base
RUN apt-get update \
    && apt-get install ca-certificates curl gnupg wget unzip sudo nano iputils-ping gcc g++ make apt-transport-https jq -yq

# java
RUN apt-get install openjdk-17-jdk-headless -yq

ARG GRADLE_VERSION=8.13
# https://developer.android.com/studio?hl=fr#command-line-tools-only
ARG ANDROID_CMDTOOLS_VERSION=14742923

ENV JAVA_HOME /usr/lib/jvm/java-17-openjdk-amd64
ENV GRADLE_USER_HOME /opt/gradle
ENV ANDROID_SDK_ROOT /usr/local/android-sdk-linux
ENV ANDROID_HOME $ANDROID_SDK_ROOT
ENV PATH $PATH:$ANDROID_SDK_ROOT/platform-tools:$ANDROID_SDK_ROOT/cmdline-tools/latest/bin:$ANDROID_SDK_ROOT/build-tools/33.0.2:$GRADLE_USER_HOME/bin

# Gradle
RUN curl -fL --retry 3 -o /tmp/gradle-${GRADLE_VERSION}-bin.zip https://downloads.gradle.org/distributions/gradle-${GRADLE_VERSION}-bin.zip && \
    unzip -qd /opt /tmp/gradle-${GRADLE_VERSION}-bin.zip && \
    ln -s /opt/gradle-${GRADLE_VERSION} /opt/gradle

# Android
RUN curl -fL --retry 3 -o /tmp/commandlinetools-linux-${ANDROID_CMDTOOLS_VERSION}_latest.zip https://dl.google.com/android/repository/commandlinetools-linux-${ANDROID_CMDTOOLS_VERSION}_latest.zip && \
    mkdir -p $ANDROID_SDK_ROOT/cmdline-tools/ && \
    unzip -qd $ANDROID_SDK_ROOT/cmdline-tools/ /tmp/commandlinetools-linux-${ANDROID_CMDTOOLS_VERSION}_latest.zip && \
    mv $ANDROID_SDK_ROOT/cmdline-tools/cmdline-tools $ANDROID_SDK_ROOT/cmdline-tools/latest

COPY android.packages android.packages
RUN ( sleep 5 && while [ 1 ]; do sleep 1; echo y; done ) | sdkmanager --package_file=android.packages

# Node.js, npm et Cordova
RUN set -eux; \
    NODE_MAJOR=24; \
    curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key \
        | gpg --dearmor -o /usr/share/keyrings/nodesource.gpg; \
    echo "deb [signed-by=/usr/share/keyrings/nodesource.gpg] https://deb.nodesource.com/node_${NODE_MAJOR}.x nodistro main" \
        > /etc/apt/sources.list.d/nodesource.list; \
    apt-get update; \
    apt-get install -y --no-install-recommends nodejs; \
    npm install -g cordova@13.0.0; \
    apt-get autoremove -y; \
    apt-get clean; \
    rm -rf /var/lib/apt/lists/*

# nettoyage du cache des paquets téléchargé
RUN rm -rf /var/lib/apt/lists/*

WORKDIR /mobile-app
