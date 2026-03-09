# TODO

Remaining work and follow-ups.

- [x] Add a new Settings page and link to it from the header menu. It should include the following:
      - Default rite (Anglican Standard Text [default] or Renewed Ancient Text), which should be used as the default in the add service modal
      - Default Bible translation (ESV [default], NRSV, or NIV) — we will reference this later, but for now just capture
      - An Integrations section that replaces the existing Integrations screen (only visible if pco_sync is enabled); this section should include the existing integration options (PCO sync) plus a default service time field (default to 10am), which should be used in the new account-specific service time default as the default in the PCO sync modal when creating a new service
      - In addition, please remove the direct link to the Integrations screen from the header menu
- [x] When creating a new user account, route the user to the Settings page after creation with a flash message indicating that the user can update the settings to reflect their needs or accept the defaults.
- [ ] Dynamically link scripture references in The Lessons service elements (1, 2, Psalter, Gospel) to Biblia deep links for the reference, based on the default Bible translation selected for the user account. For example, Psalm 1:1-3 in ESV is "https://biblia.com/books/esv/Ps1.1-3". For the translations we support, ESV = "esv", NRSV = "nrsv", and NIV = "niv2011".
- [ ] Replace "last login" on the Admin screen with the last time the user accessed the application, but only if this can be supported with an efficient and minimal DB capture of user activity.
- [ ] Add "Additional Directions" eucharistic options (see following section).
- [ ] Add "live edit" mode, in which changes can be made within the service view mode.
- [ ] PCO integration enhancements:
  - Investigate ability to use PCO templates when creating PCO services (for teams, non-order elements).
  - Investigate ability to delta update PCO services.
- [ ] Add Bible text integration options (and tie into both standard text rendering as well as live preview modals).
- [ ] Add team accounts
  - Support for shared services and element libraries.
  - Collaboration features: comments, approvals, version history.
- [ ] Add additional liturgy templates (Morning Prayer, Compline, funerals, weddings, Ash Wednesday, etc.; other prayer books/sacramentaries/missals).
- [ ] Implement additional export formats and integrations: ProPresenter, etc.

## Other eucharistic options to integrate (from "Additional Directions")

- [ ] Where the greeting “The Lord be with you” is used, the response “And also with you” may be used in place of “And with your spirit.”
- [ ] A Penitential Order, for use at the opening of the liturgy, or for use on other occasions, may be arranged as follows:
  - The Acclamation
  - The Collect for Purity
  - Then kneeling as able:
      - The Decalogue or The Summary of the Law [The Exhortation]
      - The Confession and Absolution [and Comfortable Words]
      - The Kyrie
      - The Collect of the Day
- [ ] The Athanasian Creed (page 769) may be used in place of the Nicene Creed on Trinity Sunday and other occasions as appropriate.
- [ ] The Prayers of the People in the Anglican Standard Text may be read straight through, omitting the silences and “Lord in your mercy: Hear our prayer.”
- [ ] The Exhortation is traditionally read on the First Sunday of Advent, the First Sunday in Lent, and Trinity Sunday.
- [ ] The Confession from Morning Prayer, or from either Eucharistic text, may be substituted for the one provided.
- [ ] In the Anglican Standard Text, the word “offering” may be substituted for the word “oblation.”
- [ ] In the Anglican Standard Text, it is permissible to replace the paragraph that begins “Therefore, O Lord and heavenly Father,” with this memorial acclamation:

    Celebrant
    Therefore we proclaim the mystery of faith:

    Celebrant and People
    Christ has died.
    Christ is risen.
    Christ will come again.

- [ ] In the Prayer of Humble Access, “Apart from your grace,” may be inserted at the beginning of sentence: “We are not worthy so much as to gather up the crumbs under your table; but you are the same Lord whose character is always to have mercy.”
- [ ] The words used when the Bread and Cup are given to the communicants may be taken from either Eucharistic Text.
- [ ] The Anglican Standard Text may be re-arranged to reflect the 1662 ordering as follows:
  - The Lord’s Prayer
  - The Collect for Purity
  - The Decalogue
  - The Collect of the Day
  - The Lessons
  - The Nicene Creed
  - The Sermon
  - The Offertory
  - The Prayers of the People
  - The Exhortation
  - The Confession and Absolution of Sin
  - The Comfortable Words
  - The Sursum Corda
  - The Sanctus
  - The Prayer of Humble Access
  - The Prayer of Consecration and the Ministration of Communion (ordered according to the footnote)
  - The Lord’s Prayer
  - The Post Communion Prayer
  - The Gloria in Excelsis
  - The Blessing
