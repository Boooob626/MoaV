#!/bin/sh
# MoaV Stealth: Caddy entrypoint — randomize decoy HTML, then start Caddy
set -e

TEMPLATE="/srv/template/index.html"
OUTPUT="/srv/html/index.html"

mkdir -p /srv/html

if [ -f "$TEMPLATE" ]; then
    SEED=$(od -An -N2 -tu2 /dev/urandom | tr -d ' ')

    # Site titles
    set -- \
        "Streamline" "Nextera" "Vantage" "Cirrus" \
        "Lumina" "Forge" "Mosaic" "Apex" \
        "Helix" "Pulse" "Vertex" "Orbit"
    shift $(( SEED % $# ))
    TITLE="$1"

    SEED=$(od -An -N2 -tu2 /dev/urandom | tr -d ' ')
    set -- \
        "Welcome to ${TITLE}" "${TITLE} - Digital Solutions" \
        "${TITLE} | Innovation Hub" "${TITLE} - Modern Web Services"
    shift $(( SEED % $# ))
    HEADING="$1"

    SEED=$(od -An -N2 -tu2 /dev/urandom | tr -d ' ')
    set -- \
        "Building better digital experiences" \
        "Reliable infrastructure for modern applications" \
        "Streamlined solutions for growing teams" \
        "Secure and scalable by design" \
        "Simplifying complex workflows" \
        "Performance-driven web platform"
    shift $(( SEED % $# ))
    HERO_TITLE="$1"

    SEED=$(od -An -N2 -tu2 /dev/urandom | tr -d ' ')
    set -- \
        "We help teams ship faster with tools that just work." \
        "Our platform provides the foundation your projects need to succeed." \
        "From concept to deployment, we keep things simple." \
        "Trusted by thousands of developers worldwide." \
        "Focus on what matters — we handle the rest."
    shift $(( SEED % $# ))
    HERO_DESC="$1"

    SEED=$(od -An -N2 -tu2 /dev/urandom | tr -d ' ')
    set -- \
        "Fast & Reliable" "Scalable" "Secure" \
        "Analytics" "Developer First" "Open Platform" \
        "Modern Stack" "Infrastructure" "Integration"
    shift $(( SEED % $# ))
    CARD1_TITLE="$1"

    SEED=$(od -An -N2 -tu2 /dev/urandom | tr -d ' ')
    set -- \
        "Built on proven technology with 99.9% uptime." \
        "Grows with your needs, from prototype to production." \
        "Enterprise-grade security out of the box." \
        "Real-time insights into your application performance." \
        "Clean APIs and comprehensive documentation."
    shift $(( SEED % $# ))
    CARD1_DESC="$1"

    SEED=$(od -An -N2 -tu2 /dev/urandom | tr -d ' ')
    set -- \
        "Team Collaboration" "Global CDN" "API Gateway" \
        "Cloud Native" "Monitoring" "CI/CD Pipeline"
    shift $(( SEED % $# ))
    CARD2_TITLE="$1"

    SEED=$(od -An -N2 -tu2 /dev/urandom | tr -d ' ')
    set -- \
        "Work together seamlessly with shared workspaces." \
        "Lightning-fast delivery across 200+ edge locations." \
        "Unified entry point for all your services." \
        "Designed for containers and orchestration from day one."
    shift $(( SEED % $# ))
    CARD2_DESC="$1"

    SEED=$(od -An -N2 -tu2 /dev/urandom | tr -d ' ')
    set -- \
        "24/7 Support" "Documentation" "Migration Tools" \
        "Auto Scaling" "Compliance" "Backup & Recovery"
    shift $(( SEED % $# ))
    CARD3_TITLE="$1"

    SEED=$(od -An -N2 -tu2 /dev/urandom | tr -d ' ')
    set -- \
        "Our team is always here when you need us." \
        "Comprehensive guides to get you started quickly." \
        "Seamless transition from your current provider." \
        "Automatically adjusts to traffic patterns."
    shift $(( SEED % $# ))
    CARD3_DESC="$1"

    SEED=$(od -An -N2 -tu2 /dev/urandom | tr -d ' ')
    set -- \
        "Streamline digital solutions for modern teams" \
        "Web platform and infrastructure services" \
        "Cloud-native tools for developers and teams" \
        "Build, deploy, and scale with confidence"
    shift $(( SEED % $# ))
    META_DESC="$1"

    SEED=$(od -An -N2 -tu2 /dev/urandom | tr -d ' ')
    set -- \
        "2024 ${TITLE}. All rights reserved." \
        "2025 ${TITLE}. All rights reserved." \
        "Copyright ${TITLE}." \
        "${TITLE} — Made with care."
    shift $(( SEED % $# ))
    FOOTER="$1"

    # Color themes
    SEED=$(od -An -N2 -tu2 /dev/urandom | tr -d ' ')
    THEME=$(( SEED % 6 ))
    case $THEME in
        0) BG="#f8f9fa"; TEXT="#2d3436"; ACCENT="#0984e3"; CARD_BG="#fff"; BORDER="#e0e0e0" ;;
        1) BG="#fafafa"; TEXT="#333"; ACCENT="#6c5ce7"; CARD_BG="#fff"; BORDER="#eee" ;;
        2) BG="#f5f6f7"; TEXT="#2c3e50"; ACCENT="#00b894"; CARD_BG="#fff"; BORDER="#ddd" ;;
        3) BG="#0a0a0a"; TEXT="#e0e0e0"; ACCENT="#00cec9"; CARD_BG="#1a1a1a"; BORDER="#333" ;;
        4) BG="#fafbfc"; TEXT="#24292e"; ACCENT="#0366d6"; CARD_BG="#fff"; BORDER="#e1e4e8" ;;
        5) BG="#111"; TEXT="#ccc"; ACCENT="#e17055"; CARD_BG="#1e1e1e"; BORDER="#333" ;;
    esac

    RAND_COMMENT=$(od -An -N16 -tx1 /dev/urandom | tr -d ' \n')

    sed \
        -e "s|%%TITLE%%|${TITLE}|g" \
        -e "s|%%HEADING%%|${HEADING}|g" \
        -e "s|%%HERO_TITLE%%|${HERO_TITLE}|g" \
        -e "s|%%HERO_DESC%%|${HERO_DESC}|g" \
        -e "s|%%META_DESC%%|${META_DESC}|g" \
        -e "s|%%CARD1_TITLE%%|${CARD1_TITLE}|g" \
        -e "s|%%CARD1_DESC%%|${CARD1_DESC}|g" \
        -e "s|%%CARD2_TITLE%%|${CARD2_TITLE}|g" \
        -e "s|%%CARD2_DESC%%|${CARD2_DESC}|g" \
        -e "s|%%CARD3_TITLE%%|${CARD3_TITLE}|g" \
        -e "s|%%CARD3_DESC%%|${CARD3_DESC}|g" \
        -e "s|%%FOOTER%%|${FOOTER}|g" \
        -e "s|%%BG_COLOR%%|${BG}|g" \
        -e "s|%%TEXT_COLOR%%|${TEXT}|g" \
        -e "s|%%ACCENT%%|${ACCENT}|g" \
        -e "s|%%CARD_BG%%|${CARD_BG}|g" \
        -e "s|%%BORDER%%|${BORDER}|g" \
        -e "s|%%RANDOM_COMMENT%%|${RAND_COMMENT}|g" \
        "$TEMPLATE" > "$OUTPUT"

    echo "[Stealth] Decoy site randomized (theme=$THEME, title='$TITLE')"
else
    echo "[Stealth] No template found, serving static files as-is"
fi

exec caddy run --config /etc/caddy/Caddyfile
