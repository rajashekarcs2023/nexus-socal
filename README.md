# SoCal Claude Hackathon — Chat Assistant

This assistant helps answer questions about the **SoCal Claude Hackathon** and handles event registration via Luma.

**Event page (Luma):** https://luma.com/dj0aohkq

## About
A one-day intercollegiate AI hackathon hosted by UCLA, USC, Caltech, and Nexus at UCLA's Grand Ackerman Ballroom on April 19, 2026. 100 student builders competing to build AI-powered projects for social impact, powered by Anthropic.

## What you can ask
- Event time, date, and location
- What the hackathon is about and who can participate
- Team size and team matching
- Tracks and submission requirements
- Judging criteria and prizes
- Food, WiFi, parking, and other logistics
- How to register

## Sample questions
1. When and where is the hackathon?
2. Is it free?
3. How do I register?
4. What's the team size?
5. What if I don't have a team?
6. What tracks can I build in?
7. What are the prizes?
8. Do I have to use Claude?
9. What's the application deadline?
10. Will there be food?

## Tech Stack
- **Agent framework:** Fetch.ai uAgents
- **LLM:** OpenAI (GPT) with tool-calling
- **Registration:** Luma checkout embed
- **FAQ:** Loaded from `faq.md`
- **Monitoring:** Sentry
