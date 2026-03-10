# TODO

Remaining work and follow-ups.

- [ ] Add "Additional Directions" eucharistic options (see following section).
- [ ] Fix plan element icons on mobile.
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

- [x] Where the greeting “The Lord be with you” is used, the response “And also with you” may be used in place of “And with your spirit.” [implemented as an account-level preference in Settings and applied across rendered liturgy output]
- [x] A Penitential Order, for use at the opening of the liturgy, or for use on other occasions, may be arranged as follows: [implemented via a new reordering control on /service page, with both Penitential Order and reset-to-default options]
  - The Acclamation
  - The Collect for Purity
  - Then kneeling as able:
      - The Decalogue or The Summary of the Law [The Exhortation]
      - The Confession and Absolution [and Comfortable Words]
      - The Kyrie
      - The Collect of the Day
- [ ] The Athanasian Creed (page 769) may be used in place of the Nicene Creed on Trinity Sunday and other occasions as appropriate. [add as option for all services, but retain Nicene Creed as default; also add the Apostles' Creed as an option; when implementing, ask me and I will provide the correct text for both new creeds]
- [x] The Prayers of the People in the Anglican Standard Text may be read straight through, omitting the silences and “Lord in your mercy: Hear our prayer.” [implemented as an option in the Prayers plan element for AST with dynamic text updates]
- [x] The Exhortation is traditionally read on the First Sunday of Advent, the First Sunday in Lent, and Trinity Sunday. [implemented via derived rubric hints on /service; also includes the Trinity Sunday Athanasian Creed hint]
- [ ] The Confession from Morning Prayer, or from either Eucharistic text, may be substituted for the one provided. [again, let's make this an option on the service element; I can give you the appropriate texts when we are implementing]
- [x] In the Anglican Standard Text, the word “offering” may be substituted for the word “oblation.” [implemented as a service element option on THE PRAYER OF CONSECRATION]
- [x] In the Anglican Standard Text, it is permissible to replace the paragraph that begins “Therefore, O Lord and heavenly Father,” with this memorial acclamation [implemented as a service element option]:

    Celebrant
    Therefore we proclaim the mystery of faith:

    Celebrant and People
    Christ has died.
    Christ is risen.
    Christ will come again.

- [x] In the Prayer of Humble Access, “Apart from your grace,” may be inserted at the beginning of sentence: “We are not worthy so much as to gather up the crumbs under your table; but you are the same Lord whose character is always to have mercy.” [implemented as a service element option]
- [ ] The words used when the Bread and Cup are given to the communicants may be taken from either Eucharistic Text. [this should be a service element option]
- [ ] The Anglican Standard Text may be re-arranged to reflect the 1662 ordering as follows [this should be implemented via the reordering control on /service page, as a "1662 Order", but has some complexities due to repeated elements and other changes from the base service elements as currently split in the DB]:
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
