#!/bin/bash -x

# docker.io/archlinux/archlinux:latest
DISTRO=${DISTRO:-debian}
DISTRO_TAG=${DISTRO_TAG:-12}

CONTAINER_NAME=${CONTAINER_NAME:-oudedetai_${DISTRO}_test}

./scripts/build-binary.sh

# This assumes the backend is podman

podman rm -f ${CONTAINER_NAME}
distrobox create -Y -i ${DISTRO}:${DISTRO_TAG} -n ${CONTAINER_NAME} --home `pwd`/distrobox/${DISTRO}

# XXX: consider coping the cache for some of the tests

podman cp ./dist/oudedetai ${CONTAINER_NAME}:/bin/

# First install dependencies as root - as the container may not have sudo setup
distrobox enter --additional-flags "--user root" ${CONTAINER_NAME} -- /bin/oudedetai -I -f -y --i-agree-to-faithlife-terms
# Uninstall partially to cleanup the config file that was written as root above
distrobox enter  --additional-flags "--user root" ${CONTAINER_NAME} -- sh -c "chown -R $USER: ~/"

# Then install as user normally
distrobox enter ${CONTAINER_NAME} -- /bin/oudedetai --install-app -y --i-agree-to-faithlife-terms --verbose

